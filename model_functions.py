import torch
import torch.nn as nn
import torch.nn.functional as F
from PIL import Image
from torchvision import transforms
from torchvision.models import vgg19
from torch.nn.functional import interpolate
from torchvision import models
from torchvision.models.vgg import VGG19_Weights
import os
from pytorch_msssim import SSIM

class VDSR(nn.Module):
    def __init__(self):
        super(VDSR, self).__init__()
        layers = []
        
        # Initial Convolution
        layers.append(nn.Conv2d(1, 64, kernel_size=3, padding=1))
        layers.append(nn.ReLU(inplace=True))
        layers.append(nn.BatchNorm2d(64))
        
        # Middle layers with skip connections
        for _ in range(9):  # 9 blocks of 2 layers each, making it 18 layers
            layers.append(self.make_block(64, 64))
        
        # Final Convolution
        layers.append(nn.Conv2d(64, 1, kernel_size=3, padding=1))
        
        self.layers = nn.Sequential(*layers)
        
    def make_block(self, in_channels, out_channels):
        return nn.Sequential(
            nn.Conv2d(in_channels, out_channels, kernel_size=3, padding=1),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
            nn.Conv2d(out_channels, out_channels, kernel_size=3, padding=1),
            nn.BatchNorm2d(out_channels)
        )

    def forward(self, x):
        residual = x
        out = self.layers(x)
        out += residual
        return out.clamp(0, 1)
    
class UNet(nn.Module):
    def __init__(self):
        super(UNet, self).__init__()

        # Encoder
        self.enc1 = self.conv_block(1, 32)
        self.enc2 = self.conv_block(32, 64)
        self.enc3 = self.conv_block(64, 128)
        self.enc4 = self.conv_block(128, 256)
        self.enc5 = self.conv_block(256, 512)

        # Middle
        self.middle = nn.Sequential(
            self.conv_block(512, 1024),
            nn.ConvTranspose2d(1024, 512, kernel_size=2, stride=2)
        )

        # Decoder
        self.dec5 = self.conv_block(512 + 512, 512)
        self.dec4 = self.conv_block(512 + 256, 256)
        self.dec3 = self.conv_block(256 + 128, 128)
        self.dec2 = self.conv_block(128 + 64, 64)
        self.dec1 = self.conv_block(64 + 32, 32)

        # Final Layer
        self.final_conv = nn.Conv2d(32, 1, kernel_size=1)

    def conv_block(self, in_channels, out_channels):
        return nn.Sequential(
            nn.Conv2d(in_channels, out_channels, kernel_size=3, padding=1),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
            nn.Conv2d(out_channels, out_channels, kernel_size=3, padding=1),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
        )

    def forward(self, x):
        # Encoder
        enc1 = self.enc1(x)
        enc2 = self.enc2(F.max_pool2d(enc1, 2))
        enc3 = self.enc3(F.max_pool2d(enc2, 2))
        enc4 = self.enc4(F.max_pool2d(enc3, 2))
        enc5 = self.enc5(F.max_pool2d(enc4, 2))
        
        # Middle
        middle = self.middle(F.max_pool2d(enc5, 2))
        enc5 = enc5[:, :, :middle.shape[2], :]
        middle = middle + enc5  # Skip connection

        # Decoder
        dec5 = self.dec5(torch.cat([F.interpolate(middle, size=enc5.shape[2:]), enc5], dim=1))
        dec4 = self.dec4(torch.cat([F.interpolate(dec5, size=enc4.shape[2:]), enc4], dim=1))
        dec3 = self.dec3(torch.cat([F.interpolate(dec4, size=enc3.shape[2:]), enc3], dim=1))
        dec2 = self.dec2(torch.cat([F.interpolate(dec3, size=enc2.shape[2:]), enc2], dim=1))
        dec1 = self.dec1(torch.cat([F.interpolate(dec2, size=enc1.shape[2:]), enc1], dim=1))

        # Final Layer
        final_output = self.final_conv(dec1)
        
        return final_output.clamp(0, 1)
    
def PIL_to_tensor(path):
    image = Image.open(path).convert('L')
    # Define the transformation
    transform = transforms.Compose([
        transforms.Resize((792, 612)),  # Resize to 612x792 pixels
        transforms.ToTensor()
    ])
    image_tensor = transform(image)
    return image_tensor

def tensor_to_PIL(tensor):
    tensor = tensor.squeeze().squeeze().cpu().numpy()  # Remove batch size and move to CPU
    image = Image.fromarray((tensor * 255).astype('uint8'), 'L')  # 'L' for grayscale
    return image

def load_best_model(model, directory):
    model_files = [f for f in os.listdir(directory) if f.endswith('.pth')]
    model_files.sort(key=lambda f: int(f.split('_')[2].split('.')[0]))

    if not model_files:
        print(f"No model files found in {directory}")
        return

    recent_model_path = os.path.join(directory, model_files[-1])
    save_dict = torch.load(recent_model_path)
    val_losses = save_dict.get('val_loss', [])

    if not val_losses:
        print(f"No validation loss values found in {recent_model_path}")
        return

    lowest_val_loss_epoch = val_losses.index(min(val_losses)) + 1
    best_model_file = f"model_epoch_{lowest_val_loss_epoch}.pth"
    best_model_path = os.path.join(directory, best_model_file)

    save_dict = torch.load(best_model_path)

    # Remove 'module.' prefix if present
    new_state_dict = {k.replace("module.", "").replace("_orig_mod.", ""): v for k, v in save_dict['state_dict'].items()}

    model.load_state_dict(new_state_dict)
    print(f'Model from epoch {lowest_val_loss_epoch} loaded from {best_model_path} with validation loss {min(val_losses)}')

def load_model(model, model_path):
    if not os.path.isfile(model_path):
        print(f"No model file found at {model_path}")
        return
    
    save_dict = torch.load(model_path)

    val_loss = save_dict.get('val_loss')
    if val_loss is None:
        print(f"No validation loss value found in {model_path}")
        return
    
    # Remove 'module.' prefix if present
    new_state_dict = {k.replace("module.", "").replace("_orig_mod.", ""): v for k, v in save_dict['state_dict'].items()}
    model.load_state_dict(new_state_dict)
    print(f'Model loaded from {model_path}')
    
class PerceptualLoss(nn.Module):
    def __init__(self):
        super(PerceptualLoss, self).__init__()
        self.vgg = vgg19(weights=VGG19_Weights.IMAGENET1K_V1).features
        for param in self.vgg.parameters():
            param.requires_grad = False

    def forward(self, x, y):
        x_vgg = self.vgg(x)
        y_vgg = self.vgg(y)
        loss = F.l1_loss(x_vgg, y_vgg)
        return loss    
    
class CombinedLoss(nn.Module):
    def __init__(self, alpha=1.0, beta=0.5, gamma=0.5):
        super(CombinedLoss, self).__init__()
        self.ssim_module = SSIM(data_range=1.0, size_average=True, channel=1)
        self.l1_loss = nn.L1Loss()
        self.perceptual_loss = PerceptualLoss()
        self.alpha = alpha
        self.beta = beta
        self.gamma = gamma

    def forward(self, outputs, original):
        ssim_loss = 1 - self.ssim_module(outputs, original)
        l1 = self.l1_loss(outputs, original)
        
        # Convert grayscale to 3-channel image for VGG19
        outputs_3ch = torch.cat([outputs]*3, dim=1)
        original_3ch = torch.cat([original]*3, dim=1)

        perceptual = self.perceptual_loss(outputs_3ch, original_3ch)

        loss = self.alpha * l1 + self.beta * perceptual + self.gamma * ssim_loss

        return loss