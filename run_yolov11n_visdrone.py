"""Utility to run the YOLOv11n VisDrone model on local media.

The script loads the pretrained `yolov11n-visdrone.pt` weights via Ultralytics
and runs inference on the provided source path. Results (annotated images and
text predictions) are written to a specified output directory.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import List

from ultralytics import YOLO


DEFAULT_WEIGHTS = "yolov11n-visdrone.pt"
DEFAULT_OUTPUT = "runs/visdrone"
DEFAULT_NAME = "predictions"


def parse_args() -> argparse.Namespace:
    """Build and parse the command-line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Run inference using the YOLOv11n VisDrone model on images, "
            "videos, or directories of media."
        )
    )
    parser.add_argument(
        "--source",
        type=str,
        required=True,
        help=(
            "Path to an image, video, directory, or glob pattern to run "
            "inference on."
        ),
    )
    parser.add_argument(
        "--weights",
        type=str,
        default=DEFAULT_WEIGHTS,
        help=(
            "Path to the YOLOv11n VisDrone weights. Defaults to the "
            f"pretrained '{DEFAULT_WEIGHTS}' file, which will be downloaded "
            "automatically by Ultralytics if missing."
        ),
    )
    parser.add_argument(
        "--output",
        type=str,
        default=DEFAULT_OUTPUT,
        help=(
            "Base directory for saving annotated predictions and labels. "
            f"Defaults to '{DEFAULT_OUTPUT}'."
        ),
    )
    parser.add_argument(
        "--name",
        type=str,
        default=DEFAULT_NAME,
        help=(
            "Subdirectory name under the output folder for this run. "
            f"Defaults to '{DEFAULT_NAME}'."
        ),
    )
    parser.add_argument(
        "--conf",
        type=float,
        default=0.25,
        help="Confidence threshold for filtering predictions (default: 0.25).",
    )
    parser.add_argument(
        "--imgsz",
        type=int,
        default=640,
        help="Image size for inference (default: 640).",
    )
    parser.add_argument(
        "--device",
        type=str,
        default="cpu",
        help=(
            "Computation device to use, such as 'cpu', '0' for the first GPU, "
            "or a comma-separated list of device IDs."
        ),
    )
    parser.add_argument(
        "--max-detections",
        type=int,
        default=300,
        help="Maximum number of detections per image (default: 300).",
    )

    return parser.parse_args()


def _prepare_source(source: str) -> Path:
    source_path = Path(source)
    if not source_path.exists():
        raise FileNotFoundError(f"Source path does not exist: {source_path}")
    return source_path


def _prepare_output(project: str) -> Path:
    output_path = Path(project)
    output_path.mkdir(parents=True, exist_ok=True)
    return output_path


def run_inference(
    source: str,
    weights: str = DEFAULT_WEIGHTS,
    output: str = DEFAULT_OUTPUT,
    name: str = DEFAULT_NAME,
    conf: float = 0.25,
    imgsz: int = 640,
    device: str = "cpu",
    max_detections: int = 300,
) -> List:
    """
    Run YOLOv11n VisDrone inference on the given source.

    Args:
        source: Path to an image, video, or directory containing media.
        weights: Path to the YOLOv11n VisDrone weights file.
        output: Base directory for saving prediction results.
        name: Subdirectory name within the output directory.
        conf: Confidence threshold for detections.
        imgsz: Image size for inference.
        device: Computation device string for Ultralytics.
        max_detections: Maximum detections per image.

    Returns:
        The list of prediction results returned by Ultralytics.
    """

    source_path = _prepare_source(source)
    output_path = _prepare_output(output)

    model = YOLO(weights)
    results = model.predict(
        source=str(source_path),
        save=True,
        project=str(output_path),
        name=name,
        conf=conf,
        imgsz=imgsz,
        device=device,
        max_det=max_detections,
        exist_ok=True,
    )
    return results


def main() -> None:
    args = parse_args()
    run_inference(
        source=args.source,
        weights=args.weights,
        output=args.output,
        name=args.name,
        conf=args.conf,
        imgsz=args.imgsz,
        device=args.device,
        max_detections=args.max_detections,
    )


if __name__ == "__main__":
    main()
