from PIL import Image, ImageDraw, ImageFont

# Canvas setup
width, height = 600, 400
card = Image.new("RGB", (width, height), (20, 20, 20))  # dark background
draw = ImageDraw.Draw(card)

# Load fonts (adjust path to a font available on your system)
# Larger font for SOLD
sold_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 40)
# Smaller font for other text
font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)

# Outer border
draw.rectangle([10, 10, width-10, height-10], outline=(255, 255, 255), width=2)

# Top banner box
draw.rectangle([20, 20, width-20, 60], outline=(255, 255, 255), width=2)
draw.text((30, 25), "SOLD", font=sold_font, fill=(255, 255, 255))
draw.text((width-180, 30), "for ₹ 6.7 Cr", font=font, fill=(255, 215, 0))

# Player photo placeholder
draw.rectangle([40, 100, 160, 220], outline=(150, 150, 150), width=2)
draw.text((60, 150), "Player", font=font, fill=(200, 200, 200))
draw.text((60, 170), "Photo", font=font, fill=(200, 200, 200))

# Team logo placeholder
draw.rectangle([width-160, 100, width-40, 220], outline=(150, 150, 150), width=2)
draw.text((width-140, 150), "Team", font=font, fill=(200, 200, 200))
draw.text((width-140, 170), "Logo", font=font, fill=(200, 200, 200))

# Player info
draw.text((40, 250), "Player Name / Role", font=font, fill=(255, 255, 255))

# Team info
draw.text((width-200, 250), "Team Name / CSK", font=font, fill=(255, 255, 255))

# Show the card
card.show()
