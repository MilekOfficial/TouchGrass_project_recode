from PIL import Image, ImageDraw, ImageFont
import os

def create_default_profile_image():
    # Create a 512x512 image with a green background
    size = 512
    img = Image.new('RGB', (size, size), color='#48d14b')
    draw = ImageDraw.Draw(img)
    
    # Draw a white circle in the center
    circle_size = 400
    circle_box = [(size - circle_size) // 2, (size - circle_size) // 2, 
                  (size + circle_size) // 2, (size + circle_size) // 2]
    draw.ellipse(circle_box, fill='#ffffff')
    
    # Save the image
    os.makedirs('static', exist_ok=True)
    img.save('static/default_profile.png')

def create_default_cover_image():
    # Create a 1500x500 image with a gradient from light to dark green
    width, height = 1500, 500
    img = Image.new('RGB', (width, height), color='#48d14b')
    draw = ImageDraw.Draw(img)
    
    # Create a simple gradient
    for y in range(height):
        # Interpolate between light green (top) and dark green (bottom)
        r = int(72 * (1 - y/height) + 46 * (y/height))  # 48 to 2e (46 in decimal)
        g = int(209 * (1 - y/height) + 125 * (y/height))  # d1 to 7d
        b = int(75 * (1 - y/height) + 50 * (y/height))   # 4b to 32
        draw.line([(0, y), (width, y)], fill=(r, g, b))
    
    # Add a subtle pattern
    for i in range(0, width + 100, 100):
        draw.arc([i - 100, -200, i + 100, 200], 0, 180, fill=(255, 255, 255, 25), width=5)
    
    # Save the image
    os.makedirs('static', exist_ok=True)
    img.save('static/default_cover.jpg', quality=85)

if __name__ == "__main__":
    print("Creating default profile image...")
    create_default_profile_image()
    print("Creating default cover image...")
    create_default_cover_image()
    print("Done! Default images created in the 'static' directory.")
