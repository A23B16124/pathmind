import cv2
import numpy as np

def count_mitoses(tile_rgb: np.ndarray, min_area=40, max_area=600) -> dict:
    hsv = cv2.cvtColor(tile_rgb, cv2.COLOR_RGB2HSV)
    mask = cv2.inRange(hsv, (120, 50, 30), (160, 255, 200))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    mitoses = []
    for c in contours:
        area = cv2.contourArea(c)
        if min_area < area < max_area:
            perim = cv2.arcLength(c, True)
            circularity = 4 * np.pi * area / (perim ** 2 + 1e-6)
            if circularity > 0.3:
                M = cv2.moments(c)
                mitoses.append({
                    "x": int(M["m10"] / (M["m00"] + 1e-6)),
                    "y": int(M["m01"] / (M["m00"] + 1e-6)),
                    "area": int(area),
                    "circularity": round(circularity, 3),
                })
    return {"count": len(mitoses), "detections": mitoses}
