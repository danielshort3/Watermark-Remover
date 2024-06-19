# Watermark Remover for Sheet Music

This repository contains a project aimed at removing watermarks from low-resolution sheet music and upscaling it to high-resolution images. The project uses pre-trained deep learning models (UNet and VDSR) to achieve this and includes a graphical user interface (GUI) for scraping, processing, and compiling sheet music into a PDF.

## Table of Contents

- [Introduction](#introduction)
- [Pre-trained Models](#pre-trained-models)
- [GUI Implementation](#gui-implementation)
- [Installation](#installation)
- [Usage](#usage)

## Introduction

This project aims to remove watermarks from low-resolution sheet music and upscale the images to high resolution. The process involves using a pre-trained UNet model to remove watermarks and a pre-trained VDSR model to enhance the resolution. A GUI is provided to automate the scraping, processing, and compiling of sheet music into a ready-to-use PDF.

## Pre-trained Models

The repository includes the following pre-trained models:
- UNet model for watermark removal
- VDSR model for image upscaling

These models are provided as state dictionaries and can be found in the `models/` directory.

## GUI Implementation

A GUI built with PyQt5 is used to scrape sheet music from a specified website, run it through both the UNet and VDSR models, and compile the processed images into a PDF. This implementation is found in the notebook `sheet_music_pyqt5.ipynb`.

## Installation

1. Clone the repository:
    ```bash
    git clone https://github.com/danielshort3/watermark-remover.git
    cd watermark-remover
    ```

2. Install the required packages (make sure you have `pip` and `virtualenv` installed):
    ```bash
    pip install torch torchvision
    pip install PyQt5
    pip install opencv-python
    pip install selenium
    pip install webdriver-manager
    pip install reportlab
    ```

3. Ensure the pre-trained model weights are in the `models/` directory.

## Usage

1. Launch the GUI by running the `sheet_music_pyqt5.ipynb` notebook.

2. Use the GUI to scrape sheet music from a specified website, run it through both the UNet and VDSR models, and compile the processed images into a PDF.
