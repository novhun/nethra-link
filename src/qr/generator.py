"""
generator.py
------------
QR-code generation wrapper using the `segno` library.
Produces a high-quality PNG QR code that the GUI can display.
"""

import os
import segno


def generate_qr(data: str, output_path: str, scale: int = 10) -> str:
    """
    Generate a PNG QR code encoding *data* and save it to *output_path*.

    Parameters
    ----------
    data : str
        The string to encode in the QR code (e.g. 'http://192.168.1.15:8080').
    output_path : str
        Full file path where the PNG will be written.
    scale : int
        Scale factor for the QR image (higher = larger image, default 10).

    Returns
    -------
    str
        The absolute path to the saved PNG file.
    """
    # Ensure the parent directory exists.
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    # Create the QR code with high error-correction (H) for robustness.
    qr = segno.make(data, error="H")

    # Save as PNG using the specified scale.
    qr.save(output_path, scale=scale, border=2)

    return os.path.abspath(output_path)


if __name__ == "__main__":
    path = generate_qr("http://192.168.1.15:8080", "qr_test.png")
    print(f"QR code saved at: {path}")
