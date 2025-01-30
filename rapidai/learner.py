# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/04_learner.ipynb.

# %% auto 0
__all__ = ['CancelFitException', 'CancelBatchException', 'CancelEpochException', 'Callback', 'run_cbs', 'SingleBatchCB', 'to_cpu',
           'MetricsCB', 'DeviceCB', 'TrainCB', 'ProgressCB', 'with_cbs', 'Learner', 'TrainLearner', 'MomentumLearner',
           'LRFinderCB', 'lr_find', 'WandbCB', 'EarlyStoppingCB']

# %% ../nbs/04_learner.ipynb 1
import math,torch,matplotlib.pyplot as plt
import fastcore.all as fc
from collections.abc import Mapping
from operator import attrgetter
from functools import partial
from copy import copy
import wandb
import mlflow
import mlflow.pytorch
from pathlib import Path
from torch import optim
import torch.nn.functional as F
from .conv import *
from fastprogress import progress_bar,master_bar
from torch.utils.tensorboard import SummaryWriter

# %% ../nbs/04_learner.ipynb 14
class CancelFitException(Exception): pass
class CancelBatchException(Exception): pass
class CancelEpochException(Exception): pass

# %% ../nbs/04_learner.ipynb 15
class Callback(): order = 0

# %% ../nbs/04_learner.ipynb 16
def run_cbs(cbs, method_nm, learn=None):
    for cb in sorted(cbs, key=attrgetter('order')):
        method = getattr(cb, method_nm, None)
        if method is not None: method(learn)

# %% ../nbs/04_learner.ipynb 22
class SingleBatchCB(Callback):
    order = 1
    def after_batch(self, learn): raise CancelFitException()

# %% ../nbs/04_learner.ipynb 31
from torcheval.metrics import MulticlassAccuracy,Mean

# %% ../nbs/04_learner.ipynb 34
def to_cpu(x):
    if isinstance(x, Mapping): return {k:to_cpu(v) for k,v in x.items()}
    if isinstance(x, list): return [to_cpu(o) for o in x]
    if isinstance(x, tuple): return tuple(to_cpu(list(x)))
    res = x.detach().cpu()
    return res.float() if res.dtype==torch.float16 else res

# %% ../nbs/04_learner.ipynb 35
class MetricsCB(Callback):
    def __init__(self, *ms, **metrics):
        for o in ms: metrics[type(o).__name__] = o
        self.metrics = metrics
        self.all_metrics = copy(metrics)
        self.all_metrics['loss'] = self.loss = Mean()

    def _log(self, d): print(d)
    def before_fit(self, learn): learn.metrics = self
    def before_epoch(self, learn): [o.reset() for o in self.all_metrics.values()]

    def after_epoch(self, learn):
        log = {k:f'{v.compute():.3f}' for k,v in self.all_metrics.items()}
        log['epoch'] = learn.epoch
        log['train'] = 'train' if learn.model.training else 'eval'
        self._log(log)

    def after_batch(self, learn):
        x,y,*_ = to_cpu(learn.batch)
        for m in self.metrics.values(): m.update(to_cpu(learn.preds), y)
        self.loss.update(to_cpu(learn.loss), weight=len(x))

# %% ../nbs/04_learner.ipynb 36
class DeviceCB(Callback):
    def __init__(self, device=def_device): fc.store_attr()
    def before_fit(self, learn):
        if hasattr(learn.model, 'to'): learn.model.to(self.device)
    def before_batch(self, learn): learn.batch = to_device(learn.batch, device=self.device)

# %% ../nbs/04_learner.ipynb 40
class TrainCB(Callback):
    def __init__(self, n_inp=1): self.n_inp = n_inp
    def predict(self, learn): learn.preds = learn.model(*learn.batch[:self.n_inp])
    def get_loss(self, learn): learn.loss = learn.loss_func(learn.preds, *learn.batch[self.n_inp:])
    def backward(self, learn): learn.loss.backward()
    def step(self, learn): learn.opt.step()
    def zero_grad(self, learn): learn.opt.zero_grad()

# %% ../nbs/04_learner.ipynb 42
class ProgressCB(Callback):
    order = MetricsCB.order+1
    def __init__(self, plot=False): self.plot = plot
    def before_fit(self, learn):
        learn.epochs = self.mbar = master_bar(learn.epochs)
        self.first = True
        if hasattr(learn, 'metrics'): learn.metrics._log = self._log
        self.losses = []
        self.val_losses = []

    def _log(self, d):
        if self.first:
            self.mbar.write(list(d), table=True)
            self.first = False
        self.mbar.write(list(d.values()), table=True)

    def before_epoch(self, learn): learn.dl = progress_bar(learn.dl, leave=False, parent=self.mbar)
    def after_batch(self, learn):
        learn.dl.comment = f'{learn.loss:.3f}'
        if self.plot and hasattr(learn, 'metrics') and learn.training:
            self.losses.append(learn.loss.item())
            if self.val_losses: self.mbar.update_graph([[fc.L.range(self.losses), self.losses],[fc.L.range(learn.epoch).map(lambda x: (x+1)*len(learn.dls.train)), self.val_losses]])
    
    def after_epoch(self, learn): 
        if not learn.training:
            if self.plot and hasattr(learn, 'metrics'): 
                self.val_losses.append(learn.metrics.all_metrics['loss'].compute())
                self.mbar.update_graph([[fc.L.range(self.losses), self.losses],[fc.L.range(learn.epoch+1).map(lambda x: (x+1)*len(learn.dls.train)), self.val_losses]])

# %% ../nbs/04_learner.ipynb 48
class with_cbs:
    def __init__(self, nm): self.nm = nm
    def __call__(self, f):
        def _f(o, *args, **kwargs):
            try:
                o.callback(f'before_{self.nm}')
                f(o, *args, **kwargs)
                o.callback(f'after_{self.nm}')
            except globals()[f'Cancel{self.nm.title()}Exception']: pass
            finally: o.callback(f'cleanup_{self.nm}')
        return _f

# %% ../nbs/04_learner.ipynb 49
class Learner():
    def __init__(self, model, dls=(0,), loss_func=F.mse_loss, lr=0.1, cbs=None, opt_func=optim.Adam):
        cbs = fc.L(cbs)
        fc.store_attr()

    @with_cbs('batch')
    def _one_batch(self):
        self.predict()
        self.callback('after_predict')
        self.get_loss()
        self.callback('after_loss')
        if self.training:
            self.backward()
            self.callback('after_backward')
            self.step()
            self.callback('after_step')
            self.zero_grad()

    @with_cbs('epoch')
    def _one_epoch(self):
        for self.iter,self.batch in enumerate(self.dl): self._one_batch()

    def one_epoch(self, training):
        self.model.train(training)
        self.dl = self.dls.train if training else self.dls.valid
        self._one_epoch()

    @with_cbs('fit')
    def _fit(self, train, valid):
        for self.epoch in self.epochs:
            if train: self.one_epoch(True)
            if valid: torch.no_grad()(self.one_epoch)(False)

    def fit(self, n_epochs=1, train=True, valid=True, cbs=None, lr=None):
        cbs = fc.L(cbs)
        # `add_cb` and `rm_cb` were added in lesson 18
        for cb in cbs: self.cbs.append(cb)
        try:
            self.n_epochs = n_epochs
            self.epochs = range(n_epochs)
            if lr is None: lr = self.lr
            if self.opt_func: self.opt = self.opt_func(self.model.parameters(), lr)
            self._fit(train, valid)
        finally:
            for cb in cbs: self.cbs.remove(cb)

    def __getattr__(self, name):
        if name in ('predict','get_loss','backward','step','zero_grad'): return partial(self.callback, name)
        raise AttributeError(name)

    def callback(self, method_nm): run_cbs(self.cbs, method_nm, self)
    
    @property
    def training(self): return self.model.training

# %% ../nbs/04_learner.ipynb 52
class TrainLearner(Learner):
    def predict(self): self.preds = self.model(self.batch[0])
    def get_loss(self): self.loss = self.loss_func(self.preds, self.batch[1])
    def backward(self): self.loss.backward()
    def step(self): self.opt.step()
    def zero_grad(self): self.opt.zero_grad()

# %% ../nbs/04_learner.ipynb 53
class MomentumLearner(TrainLearner):
    def __init__(self, model, dls, loss_func, lr=None, cbs=None, opt_func=optim.SGD, mom=0.85):
        self.mom = mom
        super().__init__(model, dls, loss_func, lr, cbs, opt_func)

    def zero_grad(self):
        with torch.no_grad():
            for p in self.model.parameters(): p.grad *= self.mom

# %% ../nbs/04_learner.ipynb 58
from torch.optim.lr_scheduler import ExponentialLR

# %% ../nbs/04_learner.ipynb 60
class LRFinderCB(Callback):
    def __init__(self, gamma=1.3, max_mult=3): fc.store_attr()
    
    def before_fit(self, learn):
        self.sched = ExponentialLR(learn.opt, self.gamma)
        self.lrs,self.losses = [],[]
        self.min = math.inf

    def after_batch(self, learn):
        if not learn.training: raise CancelEpochException()
        self.lrs.append(learn.opt.param_groups[0]['lr'])
        loss = to_cpu(learn.loss)
        self.losses.append(loss)
        if loss < self.min: self.min = loss
        if math.isnan(loss) or (loss > self.min*self.max_mult):
            raise CancelFitException()
        self.sched.step()

    def cleanup_fit(self, learn):
        plt.plot(self.lrs, self.losses)
        plt.xscale('log')

# %% ../nbs/04_learner.ipynb 62
@fc.patch
def lr_find(self:Learner, gamma=1.3, max_mult=3, start_lr=1e-5, max_epochs=10):
    self.fit(max_epochs, lr=start_lr, cbs=LRFinderCB(gamma=gamma, max_mult=max_mult))

# %% ../nbs/04_learner.ipynb 65
class WandbCB(Callback):
    order = MetricsCB.order + 1
    
    def __init__(self, project_name="default-project", run_name=None, log_model=True, save_model=False, model_name="final_model.pth"):
        self.project_name = project_name
        self.run_name = run_name
        self.log_model = log_model
        self.save_model = save_model
        self.model_name = model_name

    def before_fit(self, learn):
        self.run = wandb.init(project=self.project_name, name=self.run_name)
        self.run.watch(learn.model, log="all")

    def after_epoch(self, learn):
        # Log all metrics for the epoch
        metrics = {f'{k}_train' if learn.training else f'{k}_valid': v.compute().item() if hasattr(v, 'compute') else v 
                   for k, v in learn.metrics.all_metrics.items()}
        metrics["epoch"] = learn.epoch
        self.run.log(metrics)

        # Save model checkpoint if save_model is enabled
        if self.save_model and not learn.training:
            model_path = f"{self.model_name}_epoch_{learn.epoch}.pth"
            torch.save(learn.model.state_dict(), model_path)
            wandb.save(model_path)

    def after_fit(self, learn):
        if self.log_model:
            torch.save(learn.model.state_dict(), self.model_name)
            wandb.log_artifact(self.model_name, type="model")
        

    def cleanup_fit(self, learn):
        if self.log_model:
            torch.save(learn.model.state_dict(), self.model_name)
            wandb.save(self.model_name)
        self.run.finish()


class EarlyStoppingCB(Callback):
    order = MetricsCB.order+1
    def __init__(self, patience=3, min_delta=0.001):
        self.patience = patience
        self.min_delta = min_delta
        self.best_loss = float('inf')
        self.wait = 0

    def after_epoch(self, learn):
        if not learn.model.training:
            current_loss = learn.metrics.all_metrics['loss'].compute()
            if current_loss < self.best_loss - self.min_delta:
                self.best_loss = current_loss
                self.wait = 0
            else:
                self.wait += 1
            
            if self.wait >= self.patience:
                print("Early stopping triggered.")
                raise CancelFitException


