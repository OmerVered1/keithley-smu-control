"""
K2450 Control Suite - Version Information
"""

__version__ = "1.1.4"
__author__ = "Omer Vered"
__organization__ = "Ben-Gurion University of the Negev (BGU)"
__copyright__ = "Copyright 2026 Omer Vered, BGU"
__license__ = "Proprietary"
__app_name__ = "K2450 Control Suite"
__description__ = "Professional Keithley 2450 SMU Control and I-V Characterization Software"

# Build info (updated by build script)
__build_date__ = "2026-02-15"
__build_number__ = "1"

def get_version_string():
    """Return formatted version string"""
    return f"{__app_name__} v{__version__}"

def get_full_version_info():
    """Return full version information as dict"""
    return {
        "version": __version__,
        "author": __author__,
        "organization": __organization__,
        "copyright": __copyright__,
        "app_name": __app_name__,
        "description": __description__,
        "build_date": __build_date__,
        "build_number": __build_number__
    }
