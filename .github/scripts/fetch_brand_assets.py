"""Download official DHL brand assets from Wikimedia Commons and format for Home Assistant."""

import os
import urllib.request


def download_file(url: str, dest_path: str) -> None:
    headers = {
        "User-Agent": "HomeAssistant-DHL-Integration/0.1.0 (contact: github.com/FaserF/ha-dhl)"
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as resp:
        content = resp.read()
        with open(dest_path, "wb") as f:
            f.write(content)
    print(f"Downloaded {len(content)} bytes to {dest_path}")


def main() -> None:
    brand_dir = os.path.abspath(
        os.path.join(
            os.path.dirname(__file__), "..", "custom_components", "dhl", "brand"
        )
    )
    os.makedirs(brand_dir, exist_ok=True)

    # Use Wikimedia standardized thumbnail widths (500px and 250px)
    logo_2x_url = "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ac/DHL_Logo.svg/500px-DHL_Logo.svg.png"
    logo_url = "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ac/DHL_Logo.svg/250px-DHL_Logo.svg.png"

    logo_path = os.path.join(brand_dir, "logo.png")
    logo_2x_path = os.path.join(brand_dir, "logo@2x.png")

    download_file(logo_url, logo_path)
    download_file(logo_2x_url, logo_2x_path)

    icon_2x_url = "https://upload.wikimedia.org/wikipedia/commons/thumb/b/b3/DHL_Express_logo.svg/500px-DHL_Express_logo.svg.png"
    icon_url = "https://upload.wikimedia.org/wikipedia/commons/thumb/b/b3/DHL_Express_logo.svg/250px-DHL_Express_logo.svg.png"

    icon_path = os.path.join(brand_dir, "icon.png")
    icon_2x_path = os.path.join(brand_dir, "icon@2x.png")

    download_file(icon_url, icon_path)
    download_file(icon_2x_url, icon_2x_path)

    print("Successfully populated brand assets in", brand_dir)


if __name__ == "__main__":
    main()
