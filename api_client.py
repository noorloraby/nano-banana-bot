"""
Example Python client for the Nano Banana API.
Usage: python api_client.py "Your prompt here" [output.png]
"""

import requests
import sys
import os

# Configuration
API_URL = "https://api.nano-banana.co.wardksa.com/generate"
API_KEY = os.getenv("NANO_BANANA_API_KEY", "eaoepnboldkfh")


def generate_image(
    prompt: str,
    output_path: str = "output.png",
    aspect_ratio: str = None,
    quality: str = "1K",
    input_images: list = None
):
    """
    Generate an image using the Nano Banana API.
    
    Args:
        prompt: Text description for image generation
        output_path: Path to save the generated image
        aspect_ratio: Optional, 'portrait' or 'landscape'
        quality: '1K', '2K', or '4K' (default: 2K)
        input_images: Optional list of image file paths for img2img
    
    Returns:
        True if successful, False otherwise
    """
    headers = {
        "X-API-Key": API_KEY
    }
    
    # Build form data
    data = {
        "prompt": prompt,
        "quality": quality
    }
    
    if aspect_ratio:
        data["aspect_ratio"] = aspect_ratio
    
    # Handle file uploads
    files = []
    if input_images:
        for img_path in input_images:
            if os.path.exists(img_path):
                files.append(("images", open(img_path, "rb")))
    
    try:
        print(f"🎨 Generating image...")
        print(f"   Prompt: {prompt[:50]}{'...' if len(prompt) > 50 else ''}")
        print(f"   Quality: {quality}")
        if aspect_ratio:
            print(f"   Aspect: {aspect_ratio}")
        if input_images:
            print(f"   Input images: {len(input_images)}")
        
        response = requests.post(
            API_URL,
            headers=headers,
            data=data,
            files=files if files else None,
            timeout=180  # 3 minute timeout for generation
        )
        
        # Close file handles
        for _, f in files:
            f.close()
        
        if response.status_code == 200:
            # Save the image
            with open(output_path, "wb") as f:
                f.write(response.content)
            
            # Get metadata from headers
            upscaled = response.headers.get("X-Upscaled", "unknown")
            actual_quality = response.headers.get("X-Quality", "unknown")
            
            size_kb = len(response.content) / 1024
            print(f"✅ Image saved to: {output_path}")
            print(f"   Size: {size_kb:.1f} KB")
            print(f"   Upscaled: {upscaled}")
            print(f"   Quality: {actual_quality}")
            return True
        else:
            print(f"❌ Error {response.status_code}: {response.text}")
            return False
            
    except requests.exceptions.Timeout:
        print("❌ Request timed out (generation took too long)")
        return False
    except requests.exceptions.RequestException as e:
        print(f"❌ Request failed: {e}")
        return False


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python api_client.py \"Your prompt\" [output.png] [quality]")
        print("\nExamples:")
        print('  python api_client.py "A futuristic city at sunset"')
        print('  python api_client.py "A cute cat" cat.png 4K')
        sys.exit(1)
    
    prompt = sys.argv[1]
    output = sys.argv[2] if len(sys.argv) > 2 else "generated.png"
    quality = sys.argv[3] if len(sys.argv) > 3 else "2K"
    
    generate_image(prompt, output, quality=quality)
