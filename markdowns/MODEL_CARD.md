# Model Card: Kidney Segmentation U-Net

## Model Overview

**Model Name:** Kidney Segmentation U-Net  
**Version:** 1.0.0  
**Task:** Binary semantic segmentation of kidney structures in medical images  
**Framework:** PyTorch (training) → ONNX Runtime (inference)  
**Architecture:** U-Net 2D with encoder-decoder structure

## Model Details

### Architecture

- **Type:** U-Net 2D (Convolutional Neural Network)
- **Base Channels:** 64
- **Depth:** 4 encoder blocks + 1 bottleneck + 4 decoder blocks
- **Activation:** ReLU
- **Normalization:** BatchNorm2d
- **Regularization:** Dropout (p=0.1)
- **Output Activation:** Sigmoid (applied post-inference)

### Training Information

- **Loss Function:** Dice Loss (based on checkpoint filename `best_unet_dice.pth`)
- **Optimizer:** (Not specified in deployment code)
- **Training Data:** (Not specified - medical imaging dataset)
- **Validation Strategy:** (Not specified)

## Input/Output Specifications

### Input

- **Shape:** `[1, 1, 256, 256]` (batch, channels, height, width)
- **Format:** Grayscale image
- **Data Type:** `float32`
- **Value Range:** Normalized to [0, 1]
- **Preprocessing:**
  1. Convert to grayscale (if RGB/multi-channel)
  2. Min-max normalization: `(pixel - min) / (max - min)`
  3. Resize to 256×256 using LANCZOS resampling
  4. Reshape to `[1, 1, 256, 256]`

### Output

- **Shape:** `[1, 1, 256, 256]` (batch, channels, height, width)
- **Format:** Logits (before sigmoid)
- **Post-processing:**
  1. Apply sigmoid: `1 / (1 + exp(-logits))`
  2. Binary threshold at 0.5
  3. Convert to uint8 mask (0-255)
  4. Resize to original image dimensions (if needed)

### Supported Input Formats

- **File Types:** TIFF, TIF, PNG, JPEG, JPG
- **Bit Depth:** 8-bit, 16-bit (automatically converted)
- **Color Spaces:** RGB, Grayscale (automatically converted)
- **Max File Size:** 100 MB

## Performance Characteristics

### Inference Performance

- **Average Latency:** ~40-60ms (CPU, ONNX Runtime)
- **Throughput:** ~15-25 requests/second (single instance, CPU)
- **Memory Usage:** ~200-300 MB (model + runtime)
- **Model Size:** ~100 MB (ONNX format)

### Accuracy Metrics

*Note: Specific accuracy metrics should be documented from training logs*

- **Primary Metric:** Dice Score (based on checkpoint name)
- **Expected Performance:** (To be filled from validation results)
- **Limitations:** Model performance may vary with:
  - Image quality and contrast
  - Anatomical variations
  - Image acquisition parameters

## Limitations and Considerations

### Known Limitations

1. **Fixed Input Size:** Model requires 256×256 input. Larger images are downsampled, which may lose detail.
2. **Grayscale Only:** Model processes single-channel images. Multi-channel images are converted to grayscale.
3. **Binary Segmentation:** Model outputs binary mask (kidney vs. background). Does not distinguish between left/right kidney or other structures.
4. **No Confidence Scores:** Model does not provide per-pixel confidence scores.
5. **Training Data Bias:** Model performance depends on similarity to training data distribution.

### Clinical Considerations

⚠️ **IMPORTANT:** This model is for research/development purposes. For clinical use:

- Model should be validated on target population
- Results should be reviewed by qualified medical professionals
- Model should not be used as sole diagnostic tool
- Compliance with medical device regulations required

### Edge Cases

- **Low Contrast Images:** May produce incomplete segmentations
- **Artifacts:** Image artifacts (motion, noise) may affect results
- **Multiple Kidneys:** Model may segment both kidneys as single region
- **Partial Images:** Images showing only part of kidney may produce incomplete masks
- **Different Modalities:** Model trained on specific imaging modality (CT/MRI/etc.) - performance may vary on others

## Usage Guidelines

### Recommended Use Cases

- Research and development
- Educational purposes
- Preliminary segmentation for further analysis
- Integration into medical imaging workflows (with human oversight)

### Not Recommended For

- Standalone clinical diagnosis
- Automated treatment decisions
- High-stakes medical decisions without human review
- Real-time surgical guidance (without additional validation)

## Preprocessing Requirements

### Required Steps

1. **Image Loading:** Load image using PIL/Pillow
2. **Format Conversion:** Convert to grayscale if needed
3. **Normalization:** Apply min-max normalization
4. **Resizing:** Resize to 256×256 (preserve aspect ratio if needed)
5. **Type Conversion:** Convert to float32 array

### Example Preprocessing

```python
from PIL import Image
import numpy as np

# Load image
image = Image.open("kidney_image.tiff")

# Convert to grayscale
image = image.convert('L')

# Normalize
img_array = np.array(image, dtype=np.float32)
img_min, img_max = img_array.min(), img_array.max()
img_normalized = (img_array - img_min) / (img_max - img_min)

# Resize to 256x256
img_resized = image.resize((256, 256), Image.Resampling.LANCZOS)
img_array = np.array(img_resized, dtype=np.float32) / 255.0

# Reshape for model
input_tensor = img_array.reshape(1, 1, 256, 256)
```

## Post-processing

### Standard Post-processing

1. Apply sigmoid to logits
2. Threshold at 0.5
3. Convert to binary mask (0 or 255)
4. Optionally resize to original image dimensions

### Optional Enhancements

- Morphological operations (opening, closing) to smooth mask
- Connected component analysis to filter small regions
- Contour extraction for boundary visualization

## Model Files

- **Training Checkpoint:** `backend/models/best_unet_dice.pth` (PyTorch)
- **ONNX Model:** `backend/models/kidney_segmentation.onnx` (Production)
- **ONNX Opset Version:** 17
- **Conversion Script:** `backend/convert_to_onnx.py`

## Deployment Information

- **Runtime:** ONNX Runtime 1.17.0+
- **Providers:** CPUExecutionProvider (default), CUDAExecutionProvider (if GPU available)
- **API Endpoint:** `POST /api/predict`
- **Model Info Endpoint:** `GET /model-info`

## Maintenance and Updates

- **Model Versioning:** Semantic versioning (currently 1.0.0)
- **Update Process:** Retrain → Convert to ONNX → Deploy
- **Backward Compatibility:** API maintains consistent input/output format

## References

- U-Net Architecture: [Ronneberger et al., 2015](https://arxiv.org/abs/1505.04597)
- ONNX Runtime: https://onnxruntime.ai/
- Model Card Template: https://modelcards.withgoogle.com/about

## Contact and Support

For questions about model usage, limitations, or deployment:
- Check API documentation: `http://localhost:8000/docs`
- Review backend README: `backend/README.md`
- Review deployment roadmap: `Deployment-Roadmap.md`

---

**Last Updated:** 2024  
**Model Card Version:** 1.0.0

