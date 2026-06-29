---
name: plate-recognition
description: Chinese license plate recognition pipeline using OpenCV + SVM + LLM verification. Supports preprocessing, license plate location, character segmentation, SVM recognition, LLM ambiguity resolution, and blacklist checking.
---

## Overview

Complete Chinese license plate (blue plate) recognition pipeline. This skill
orchestrates a 6-stage GraphAgent pipeline: preprocessing, license plate
location, character segmentation, SVM recognition, LLM verification for
low-confidence characters, and blacklist lookup via ChromaDB RAG.

## Pipeline Stages

| Stage | Tool | Description |
|-------|------|-------------|
| 1. Preprocess | gaussian_blur, grayscale, binarize_otsu, edge_detect_canny, affine_correct | Image enhancement and perspective correction |
| 2. Locate | morphology_locate, color_locate | Morphological + HSV-based license plate location |
| 3. Segment | vertical_projection | Character segmentation via vertical projection |
| 4. Recognize | svm_predict | SVM-based character recognition with confidence scoring |
| 5. LLM Verify | llm_verify, lookup_confusion | LLM-based verification for low-confidence characters (DeepSeek) |
| 6. Format | search_blacklist | ChromaDB blacklist lookup and response formatting |

## Tools

This skill exposes the following FunctionTools when loaded:

- plate_preprocess: Run full preprocessing pipeline on an image
- plate_locate: Locate license plate region in preprocessed image
- plate_segment: Segment characters from located plate region
- plate_recognize: Recognize plate characters using SVM
- plate_verify: LLM-based verification of recognition results
- plate_blacklist_check: Check recognized plate against blacklist database

## Usage Pattern

1. Load the skill:
   `
   skill_load(skill="plate-recognition", include_all_docs=True)
   `

2. Run the recognition pipeline:
   `
   plate_preprocess(image_path="/data/car.jpg")
   plate_locate(image_path="...")
   plate_segment(image_path="...")
   plate_recognize(char_images=[...])
   plate_verify(svm_results=[...])
   plate_blacklist_check(plate="JingA12345")
   `

## Examples

Example 1: Full pipeline recognition

   Command:

   python3 scripts/recognize_plate.py \
     --image work/inputs/car.jpg \
     --output out/result.json

Example 2: Batch recognition

   Command:

   python3 scripts/batch_recognize.py \
     --input-dir work/inputs/batch/ \
     --output-dir out/batch_results/

Example 3: Single character debug

   Command:

   python3 scripts/debug_char.py \
     --image work/inputs/char_3.jpg \
     --output out/debug_char_3.json

## Output Files

- out/result.json: Single image recognition result with confidence scores
- out/batch_results/: Batch recognition results directory
- out/debug_char_*.json: Per-character debug information

## Dependencies

- opencv-python>=4.8.0
- numpy>=1.24.0
- scikit-learn>=1.3.0
- openai>=1.30.0 (for LLM verification via DeepSeek)
- chromadb>=0.4.0 (for blacklist RAG)