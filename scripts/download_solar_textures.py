"""Fetch the attributed CC BY 4.0 maps used by the local 3D viewer."""
from pathlib import Path
import io
import httpx
import truststore
import ssl
from PIL import Image

FILES = {'mercury':'mercury','venus':'venus_atmosphere','earth':'earth_daymap',
         'mars':'mars','jupiter':'jupiter','saturn':'saturn','uranus':'uranus',
         'neptune':'neptune','sun':'sun','moon':'moon'}

if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1] / 'frontend/public/textures/solar'
    root.mkdir(parents=True, exist_ok=True)
    with httpx.Client(verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT),timeout=40,follow_redirects=False) as client:
        for key, source in FILES.items():
            path = root / (key+'.jpg')
            if path.is_file():
                with Image.open(path) as image: image.verify()
                print(key,'present'); continue
            response=client.get(f'https://www.solarsystemscope.com/textures/download/2k_{source}.jpg')
            response.raise_for_status()
            if len(response.content)>10_000_000: raise ValueError('Texture exceeds budget')
            with Image.open(io.BytesIO(response.content)) as image: image.verify()
            path.write_bytes(response.content)
            print(key,len(response.content))
