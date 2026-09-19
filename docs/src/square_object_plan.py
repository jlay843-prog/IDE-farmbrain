"""
2x2 Square Object Plan

This script defines the specifications and parameters for a 2x2 inch square object.
The plan includes dimensions, material considerations, and implementation notes.
"""

class SquareObject:
    """
    A class representing a 2x2 inch square object.
    
    Attributes:
        width (float): Width of the square in inches
        height (float): Height of the square in inches
        depth (float): Depth/thickness of the square in inches
        material (str): Material type for the object
        tolerance (float): Manufacturing tolerance in inches
    """
    
    def __init__(self, width=2.0, height=2.0, depth=0.125, material="plastic", tolerance=0.005):
        """
        Initialize the SquareObject with specified dimensions.
        
        Args:
            width (float): Width in inches (default: 2.0)
            height (float): Height in inches (default: 2.0)
            depth (float): Depth in inches (default: 0.125 for 1/8 inch)
            material (str): Material type (default: plastic)
            tolerance (float): Manufacturing tolerance in inches (default: 0.005)
        """
        self.width = width
        self.height = height
        self.depth = depth
        self.material = material
        self.tolerance = tolerance

    def get_volume(self):
        """Calculate and return the volume of the square object."""
        return self.width * self.height * self.depth

    def get_surface_area(self):
        """Calculate and return the surface area of the square object."""
        return 2 * (self.width * self.height + 
                   self.width * self.depth + 
                   self.height * self.depth)

    def __str__(self):
        """String representation of the SquareObject."""
        return f"SquareObject({self.width}x{self.height}x{self.depth} inches, {self.material})"

# Example usage
if __name__ == "__main__":
    # Create a 2x2 square object with default parameters
    square = SquareObject()
    
    print(f"Object: {square}")
    print(f"Volume: {square.get_volume()} cubic inches")
    print(f"Surface Area: {square.get_surface_area()} square inches")

    # Create a custom 2x2 object with different material
    custom_square = SquareObject(material="aluminum")
    print(f"Custom Object: {custom_square}")
