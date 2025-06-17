import numpy as np
from scipy.optimize import curve_fit

class twoDfittings:
    """Class containing 2D fitting methods for raster scan data (STM, Optical Intensity, etc.)."""

    @staticmethod
    def raw(data):
        """Returns the raw, unmodified data."""
        return data

    @staticmethod
    def subtract_background(data):
        """Subtracts the minimum value from the data."""
        min_value = np.min(data)
        return data - min_value + 124
        
    @staticmethod
    def subtract_average(data):
        """Subtracts the mean value from the data."""
        mean_value = np.mean(data)
        return data - mean_value

    @staticmethod
    def subtract_slope(data):
        """Subtracts a slope estimated from the average of each row."""
        rows, cols = data.shape
        x = np.arange(cols)
        slope_corrected_data = np.zeros_like(data)

        for i in range(rows):
            slope = np.polyfit(x, data[i, :], 1)  # Linear fit (degree 1)
            slope_corrected_data[i, :] = data[i, :] - (slope[0] * x + slope[1])  # Subtract the slope

        return slope_corrected_data

    @staticmethod
    def subtract_linear_fit(data):
        """Performs a least-squares linear plane fit and subtracts it."""
        rows, cols = data.shape
        x, y = np.meshgrid(np.arange(cols), np.arange(rows))

        def linear_plane(coords, a, b, c):
            """Linear plane function: z = a*x + b*y + c"""
            x, y = coords
            return a*x + b*y + c

        # Fit the data
        params, _ = curve_fit(linear_plane, (x.ravel(), y.ravel()), data.ravel())

        # Compute fitted plane
        fitted_plane = linear_plane((x, y), *params)

        return data - fitted_plane

    @staticmethod
    def subtract_parabolic_fit(data):
        """Fits and subtracts a parabolic surface from the data."""
        rows, cols = data.shape
        x, y = np.meshgrid(np.arange(cols), np.arange(rows))

        def parabolic_surface(coords, a, b, c, d, e, f):
            """Parabolic surface function: z = a*x^2 + b*y^2 + c*x*y + d*x + e*y + f"""
            x, y = coords
            return a*x**2 + b*y**2 + c*x*y + d*x + e*y + f

        # Fit the data
        params, _ = curve_fit(parabolic_surface, (x.ravel(), y.ravel()), data.ravel())

        # Compute fitted parabolic surface
        fitted_parabola = parabolic_surface((x, y), *params)

        return data - fitted_parabola