import numpy as np, tifffile, pathlib

pathlib.Path("tests/fixtures").mkdir(parents=True, exist_ok=True)
data = np.random.randint(180, 255, (1024, 1024, 3), dtype=np.uint8)
data[200:600, 200:600] = [160, 100, 180]

with tifffile.TiffWriter("tests/fixtures/mini_slide.tiff", bigtiff=True) as tif:
    options = dict(photometric="rgb", tile=(256, 256), compression="zlib")
    tif.write(data, subifds=2, **options)
    tif.write(data[::2, ::2], subfiletype=1, **options)
    tif.write(data[::4, ::4], subfiletype=1, **options)

print("fixture ok")
