import cv2
import numpy as np
import os

def remove_background(input_path, output_path):
    # Load image
    img = cv2.imread(input_path, cv2.IMREAD_UNCHANGED)
    if img is None:
        print("Error: Could not load image")
        return

    # If no alpha channel, add one
    if img.shape[2] == 3:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)

    # Define the white background range (adjust if necessary)
    # We look for pixels that are very close to white (240-255)
    lower_white = np.array([240, 240, 240, 255])
    upper_white = np.array([255, 255, 255, 255])

    # Create a mask for white pixels
    white_mask = cv2.inRange(img, lower_white, upper_white)

    # Set alpha to 0 where the mask is white
    img[white_mask > 0, 3] = 0

    # Optional: Smooth edges slightly
    # img = cv2.GaussianBlur(img, (3, 3), 0)

    # Save the result
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    cv2.imwrite(output_path, img)
    print(f"Success: Transparent icon saved to {output_path}")

if __name__ == "__main__":
    raw_path = r"C:\Users\HUN\.gemini\antigravity\brain\2ad47e90-d295-480d-9e77-9afade1953c0\nethralink_raw_icon_1777055960107.png"
    target_path = "assets/icon.png"
    remove_background(raw_path, target_path)
