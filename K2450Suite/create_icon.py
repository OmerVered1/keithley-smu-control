"""
Generate application icon for K2450 Control Suite
"""

from PIL import Image, ImageDraw, ImageFont
import os

def create_icon():
    """Create a modern icon for the K2450 Control Suite"""
    
    # Create icon at multiple sizes for .ico file
    sizes = [16, 32, 48, 64, 128, 256]
    images = []
    
    for size in sizes:
        # Create new image with transparent background
        img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        # Background - gradient-like blue circle
        margin = int(size * 0.05)
        draw.ellipse(
            [margin, margin, size - margin, size - margin],
            fill='#1565C0',  # Blue
            outline='#0D47A1'  # Darker blue outline
        )
        
        # Add inner highlight
        inner_margin = int(size * 0.1)
        draw.ellipse(
            [inner_margin, inner_margin, size - inner_margin, size - inner_margin],
            fill='#1976D2'  # Slightly lighter blue
        )
        
        # Draw "K" letter or simplified SMU symbol
        if size >= 32:
            # For larger sizes, draw a "K" or stylized I-V curve
            center_x, center_y = size // 2, size // 2
            
            # Draw stylized I-V curve (sine-like wave)
            points = []
            for i in range(20):
                x = margin + int((size - 2*margin) * i / 19)
                # Sinusoidal curve
                progress = i / 19
                y = center_y + int((size * 0.25) * (0.5 - progress) * 2)
                points.append((x, y))
            
            # Draw the curve
            line_width = max(1, size // 16)
            if len(points) > 1:
                for i in range(len(points) - 1):
                    draw.line([points[i], points[i+1]], fill='#FFFFFF', width=line_width)
            
            # Draw axes
            ax_margin = int(size * 0.2)
            # Y-axis (vertical)
            draw.line(
                [(ax_margin, ax_margin), (ax_margin, size - ax_margin)],
                fill='#BBDEFB', width=max(1, line_width // 2)
            )
            # X-axis (horizontal)
            draw.line(
                [(ax_margin, size - ax_margin), (size - ax_margin, size - ax_margin)],
                fill='#BBDEFB', width=max(1, line_width // 2)
            )
        
        images.append(img)
    
    # Save as ICO
    output_dir = os.path.dirname(os.path.abspath(__file__))
    resources_dir = os.path.join(output_dir, 'resources')
    os.makedirs(resources_dir, exist_ok=True)
    
    ico_path = os.path.join(resources_dir, 'k2450_icon.ico')
    
    # Save the largest image, then save as ico with all sizes
    images[-1].save(
        ico_path,
        format='ICO',
        sizes=[(s, s) for s in sizes]
    )
    
    print(f"Icon saved to: {ico_path}")
    
    # Also save a PNG version for reference
    png_path = os.path.join(resources_dir, 'k2450_icon.png')
    images[-1].save(png_path, format='PNG')
    print(f"PNG saved to: {png_path}")
    
    return ico_path


def create_simple_icon():
    """Create a simpler, cleaner icon"""
    sizes = [16, 32, 48, 64, 128, 256]
    images = []
    
    for size in sizes:
        img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        # Blue rounded rectangle background
        margin = int(size * 0.08)
        radius = int(size * 0.15)
        
        # Draw rounded rectangle
        draw.rounded_rectangle(
            [margin, margin, size - margin, size - margin],
            radius=radius,
            fill='#1565C0',
            outline='#0D47A1',
            width=max(1, size // 32)
        )
        
        # Inner lighter area
        inner_margin = int(size * 0.15)
        inner_radius = int(size * 0.1)
        draw.rounded_rectangle(
            [inner_margin, inner_margin, size - inner_margin, size - inner_margin],
            radius=inner_radius,
            fill='#1976D2'
        )
        
        # Draw stylized "IV" curve (diagonal line with arrow)
        if size >= 24:
            line_width = max(1, size // 12)
            
            # Starting point (bottom-left)
            x1 = int(size * 0.25)
            y1 = int(size * 0.75)
            # End point (top-right)  
            x2 = int(size * 0.75)
            y2 = int(size * 0.25)
            
            # Draw main diagonal line (I-V characteristic)
            draw.line([(x1, y1), (x2, y2)], fill='#FFFFFF', width=line_width)
            
            # Draw axes in lighter color
            ax_x = int(size * 0.2)
            ax_y = int(size * 0.8)
            ax_width = max(1, line_width // 2)
            
            # Y-axis
            draw.line([(ax_x, int(size * 0.2)), (ax_x, ax_y)], fill='#90CAF9', width=ax_width)
            # X-axis
            draw.line([(ax_x, ax_y), (int(size * 0.8), ax_y)], fill='#90CAF9', width=ax_width)
        
        images.append(img)
    
    # Save
    output_dir = os.path.dirname(os.path.abspath(__file__))
    resources_dir = os.path.join(output_dir, 'resources')
    os.makedirs(resources_dir, exist_ok=True)
    
    ico_path = os.path.join(resources_dir, 'k2450_icon.ico')
    
    # Save as ICO with all sizes
    images[-1].save(
        ico_path,
        format='ICO',
        sizes=[(s, s) for s in sizes]
    )
    
    print(f"Icon saved to: {ico_path}")
    
    # PNG for reference
    png_path = os.path.join(resources_dir, 'k2450_icon.png')
    images[-1].save(png_path, format='PNG')
    print(f"PNG saved to: {png_path}")
    
    return ico_path


if __name__ == "__main__":
    create_simple_icon()
