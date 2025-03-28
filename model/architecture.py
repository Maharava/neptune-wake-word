"""
CNN model architecture for wake word detection
"""
import torch
import torch.nn as nn
import torch.nn.functional as F
import logging
import os
import math
from pathlib import Path

logger = logging.getLogger("Io.Model.Architecture")

def calculate_conv_output_length(input_length, kernel_size, stride, padding=0):
    """Calculate output length after a conv/pool layer with precise PyTorch formula"""
    return math.floor((input_length + 2 * padding - kernel_size) / stride + 1)


class SimpleWakeWordModel(nn.Module):
    """Simplified CNN model for wake word detection"""
    
    def __init__(self, n_mfcc=13, num_frames=101):
        super(SimpleWakeWordModel, self).__init__()
        
        # A simpler architecture with fewer layers
        self.conv_layer = nn.Sequential(
            nn.Conv1d(n_mfcc, 32, kernel_size=3, stride=1, padding=1),
            nn.ReLU(),
            nn.MaxPool1d(kernel_size=3, stride=2, padding=0)
        )
        
        # Calculate output size
        output_width = calculate_conv_output_length(num_frames, 3, 2, 0)
        self.fc_input_size = 32 * output_width
        
        self.fc_layers = nn.Sequential(
            nn.Linear(self.fc_input_size, 64),
            nn.ReLU(),
            nn.Linear(64, 1),
            nn.Sigmoid()
        )
    
    def forward(self, x):
        x = self.conv_layer(x)
        x = x.view(x.size(0), -1)
        x = self.fc_layers(x)
        return x


class WakeWordModel(nn.Module):
    """1D CNN model for wake word detection"""
    
    def __init__(self, n_mfcc=13, num_frames=101):
        """Initialize the model with given parameters"""
        super(WakeWordModel, self).__init__()
        
        # Calculate exact output dimensions for each layer
        # First MaxPool: kernel=3, stride=2, padding=0
        after_pool1 = calculate_conv_output_length(num_frames, 3, 2, 0)
        # Second MaxPool: kernel=3, stride=2, padding=0
        after_pool2 = calculate_conv_output_length(after_pool1, 3, 2, 0)
        # Final flattened size
        self.fc_input_size = 64 * after_pool2
        
        logger.info(f"Model dimensions calculation: input={num_frames}, after_pool1={after_pool1}, "
                   f"after_pool2={after_pool2}, fc_input_size={self.fc_input_size}")
        
        # Simplified architecture with clear dimensions tracking
        self.conv_layers = nn.Sequential(
            # First conv block - ensure n_mfcc is used here as input channels
            nn.Conv1d(n_mfcc, 64, kernel_size=3, stride=1, padding=1),
            nn.BatchNorm1d(64),
            nn.ReLU(),
            nn.MaxPool1d(kernel_size=3, stride=2, padding=0),
            
            # Second conv block
            nn.Conv1d(64, 64, kernel_size=3, stride=1, padding=1),
            nn.BatchNorm1d(64),
            nn.ReLU(),
            nn.MaxPool1d(kernel_size=3, stride=2, padding=0)
        )
        
        # Fully connected layers
        self.fc_layers = nn.Sequential(
            nn.Linear(self.fc_input_size, 128),
            nn.ReLU(),
            nn.Linear(128, 1),
            nn.Sigmoid()
        )
    
    def forward(self, x):
        """Forward pass through the model"""
        # Apply conv layers
        x = self.conv_layers(x)
        
        # Log shape for debugging
        batch_size, channels, width = x.shape
        logger.debug(f"Shape before flattening: {x.shape}")
        
        # Verify dimensions match what we calculated
        expected_size = self.fc_input_size // channels
        if width != expected_size:
            logger.warning(f"Dimension mismatch! Expected width: {expected_size}, got: {width}")
        
        # Flatten for FC layers
        x = x.view(x.size(0), -1)
        
        # Apply FC layers
        x = self.fc_layers(x)
        
        return x


def create_model(n_mfcc=13, num_frames=101, simple=False):
    """Create a new wake word model"""
    if simple:
        return SimpleWakeWordModel(n_mfcc=n_mfcc, num_frames=num_frames)
    else:
        return WakeWordModel(n_mfcc=n_mfcc, num_frames=num_frames)


def save_model(model, path):
    """Save model to disk with proper resource management"""
    try:
        if model is None:
            logger.error("Cannot save None model")
            return False
            
        # Ensure the directory exists
        path = Path(path) if not isinstance(path, Path) else path
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # Save the model state dict
        torch.save(model.state_dict(), path)
        logger.info(f"Model saved to {path}")
        
        # Save model info for reference
        try:
            info_path = path.parent / f"{path.stem}_info.txt"
            with open(info_path, 'w') as f:
                model_type = "simple" if isinstance(model, SimpleWakeWordModel) else "standard"
                f.write(f"Model type: {model_type}\n")
                f.write(f"Save date: {__import__('datetime').datetime.now()}\n")
        except Exception as e:
            logger.warning(f"Error saving model info: {e}")
            
        return True
    except Exception as e:
        logger.error(f"Error saving model: {e}")
        return False


def load_model(path, n_mfcc=13, num_frames=101):
    """Load model from disk with automatic architecture detection"""
    if not path:
        logger.error("Model path is None")
        return None
    
    # Convert to Path object and check if it exists
    path = Path(path) if not isinstance(path, Path) else path
    
    if not path.exists():
        logger.error(f"Model file not found: {path}")
        return None
    
    try:
        # Load state dictionary to check architecture
        state_dict = torch.load(path, map_location=torch.device('cpu'))
        
        # Check for model architecture by examining state_dict keys
        is_simple_model = any('conv_layer' in key for key in state_dict.keys())
        logger.info(f"Detected {'SimpleWakeWordModel' if is_simple_model else 'WakeWordModel'} architecture")
        
        # Create the appropriate model based on detected architecture
        if is_simple_model:
            logger.info(f"Creating SimpleWakeWordModel with n_mfcc={n_mfcc}, num_frames={num_frames}")
            model = SimpleWakeWordModel(n_mfcc=n_mfcc, num_frames=num_frames)
        else:
            logger.info(f"Creating WakeWordModel with n_mfcc={n_mfcc}, num_frames={num_frames}")
            model = WakeWordModel(n_mfcc=n_mfcc, num_frames=num_frames)
        
        # Try loading the state dict
        try:
            model.load_state_dict(state_dict)
        except Exception as e:
            logger.error(f"Error loading state dict: {e}")
            logger.warning("This might be due to model architecture mismatch. Trying the other architecture...")
            
            # Try the other architecture
            if is_simple_model:
                model = WakeWordModel(n_mfcc=n_mfcc, num_frames=num_frames)
            else:
                model = SimpleWakeWordModel(n_mfcc=n_mfcc, num_frames=num_frames)
                
            try:
                model.load_state_dict(state_dict)
                logger.info("Successfully loaded with alternate architecture")
            except Exception as e2:
                logger.error(f"Failed with alternate architecture too: {e2}")
                return None
        
        # Set to evaluation mode
        model.eval()
        
        logger.info(f"Model loaded successfully from {path}")
        return model
        
    except Exception as e:
        logger.error(f"Error loading model: {e}")
        return None