#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
import struct
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]


def read_idx_images(path: Path) -> np.ndarray:
    with gzip.open(path, "rb") as file:
        magic, count, rows, cols = struct.unpack(">IIII", file.read(16))
        if magic != 2051:
            raise ValueError(f"{path} is not an IDX image file")
        data = np.frombuffer(file.read(), dtype=np.uint8)
    expected = count * rows * cols
    if data.size != expected:
        raise ValueError(f"{path} has {data.size} image bytes, expected {expected}")
    return data.reshape(count, rows, cols)


def read_idx_labels(path: Path) -> np.ndarray:
    with gzip.open(path, "rb") as file:
        magic, count = struct.unpack(">II", file.read(8))
        if magic != 2049:
            raise ValueError(f"{path} is not an IDX label file")
        data = np.frombuffer(file.read(), dtype=np.uint8)
    if data.size != count:
        raise ValueError(f"{path} has {data.size} labels, expected {count}")
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert standard MNIST IDX gzip files to data/mnist.npz.")
    parser.add_argument("--mnist-dir", default=str(ROOT / "MNIST"))
    parser.add_argument("--output", default=str(ROOT / "data" / "mnist.npz"))
    args = parser.parse_args()

    mnist_dir = Path(args.mnist_dir)
    output = Path(args.output)
    files = {
        "x_train": mnist_dir / "train-images-idx3-ubyte.gz",
        "y_train": mnist_dir / "train-labels-idx1-ubyte.gz",
        "x_test": mnist_dir / "t10k-images-idx3-ubyte.gz",
        "y_test": mnist_dir / "t10k-labels-idx1-ubyte.gz",
    }
    missing = [path for path in files.values() if not path.exists()]
    if missing:
        raise FileNotFoundError("missing MNIST files: " + ", ".join(str(path) for path in missing))

    x_train = read_idx_images(files["x_train"])
    y_train = read_idx_labels(files["y_train"])
    x_test = read_idx_images(files["x_test"])
    y_test = read_idx_labels(files["y_test"])
    output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(output, x_train=x_train, y_train=y_train, x_test=x_test, y_test=y_test)
    print(f"wrote {output.resolve()}")
    print(f"x_train={x_train.shape}, y_train={y_train.shape}, x_test={x_test.shape}, y_test={y_test.shape}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
