
# RapidAI

**RapidAI** is a Python library built on top of **PyTorch**, designed to streamline the process of training machine learning models. It simplifies workflows by offering modular APIs for model initialization, training, evaluation, and data handling.

## Installation

Use the package manager [pip](https://pip.pypa.io/en/stable/) to install RapidAI:

```bash
pip install rapidai
```

Make sure you have **Python 3.8+** and **PyTorch** installed before installing RapidAI.

## Usage

Below is an example of how to load data, initialize a model, and train it using RapidAI:

```python
from rapidai.core import initialize_weights
from rapidai.datasets import load_mnist
from rapidai.training import train_model

# Load the MNIST dataset
train_loader, val_loader = load_mnist(batch_size=32)

# Define a custom CNN model
model = MyCustomCNN()

# Initialize the model’s weights
initialize_weights(model)

# Train the model for 10 epochs
train_model(model, train_loader, val_loader, epochs=10)
```

## Modules and Functions

### Core Utilities (`core.py`)
- **`initialize_weights(model)`**: Initializes the weights for better convergence.
- **`train_model()`**: Manages training loops and backpropagation.

### Dataset Handling (`datasets.py`)
- **`load_mnist(batch_size=32)`**: Loads and preprocesses the MNIST dataset.
- **`split_data()`**: Splits data into train, validation, and test sets.

### Training Management (`training.py`)
- **`train_one_epoch()`**: Runs a single epoch of training.
- **`evaluate_model()`**: Evaluates model performance on validation/test data.

### Neural Networks (`conv.py`, `resnet.py`)
- **`conv.py`**: Functions for building convolutional layers.
- **`resnet.py`**: Pre-built ResNet architectures for transfer learning.

### Learner and Optimization (`learner.py`, `accel.py`)
- **`learner.py`**: Encapsulates the training process with metric tracking.
- **`accel.py`**: Optimized implementations of SGD for faster convergence.

### Data Augmentation and Activation Functions
- **`augment.py`**: Tools for augmenting data with techniques like random flipping.
- **`activations.py`**: Implements ReLU, Sigmoid, Tanh, and other activations.

## Example Notebooks

The following Jupyter notebooks in the repository demonstrate the use of RapidAI:
- **00_core.ipynb**: Overview of the core functionalities.  
- **01_minibatch_training.ipynb**: Setting up minibatch training workflows.  
- **04_learner.ipynb**: Using the `learner` module for training.  
- **08_resnet.ipynb**: Transfer learning with a ResNet model.

## Contributing

Pull requests are welcome! For major changes, please open an issue first to discuss what you would like to change.

Make sure to update tests as appropriate when contributing.

## License

[MIT](https://choosealicense.com/licenses/mit/)
