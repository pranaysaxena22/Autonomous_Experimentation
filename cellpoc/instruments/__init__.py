"""The instruments (new part, 2026-10-14): drivers for the devices the cell reads, each with a simulated version now and a serial version for real hardware, behind one interface.

The barcode scanner and the balance. Everything here is plain Python with no other part of the project imported, and nothing here touches the network. The executor uses these interfaces, so the simulation and a real cell make
the same decisions (is this the right vial? is the weighed amount within tolerance?) from the same code; only the device behind the interface changes. See docs/hardware_pipeline.md for how a real device is connected.
"""
from .balance import Balance, SicsBalance, SimulatedBalance, Weight, dose_check
from .barcode import BarcodeScanner, ScanResult, SerialBarcodeScanner, SimulatedBarcodeScanner, classify
from .kit import Instruments
from .labels import LabelFormat, format_from_layout
from .transport import FakeTransport, SerialTransport, Transport, TransportError

__all__ = ["Balance", "BarcodeScanner", "FakeTransport", "Instruments", "LabelFormat", "ScanResult", "SerialBarcodeScanner", "SerialTransport", "SicsBalance", "SimulatedBalance", "SimulatedBarcodeScanner", "Transport",
           "TransportError", "Weight", "classify", "dose_check", "format_from_layout"]
