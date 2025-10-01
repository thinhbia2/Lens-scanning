import clr
import os
import time
from System import Decimal

kinesis_path = r"C:\Program Files\Thorlabs\Kinesis"
os.environ["PATH"] += os.pathsep + kinesis_path

# Load DLLs
clr.AddReference(os.path.join(kinesis_path, "Thorlabs.MotionControl.DeviceManagerCLI.dll"))
clr.AddReference(os.path.join(kinesis_path, "Thorlabs.MotionControl.GenericMotorCLI.dll"))
clr.AddReference(os.path.join(kinesis_path, "Thorlabs.MotionControl.KCube.DCServoCLI.dll"))

from Thorlabs.MotionControl.DeviceManagerCLI import DeviceManagerCLI
from Thorlabs.MotionControl.KCube.DCServoCLI import KCubeDCServo
from Thorlabs.MotionControl.GenericMotorCLI.ControlParameters import VelocityParameters


class KDC101Controller:
    def __init__(self):
        self.device = None
        self.serial = None

    def connect(self):
        DeviceManagerCLI.BuildDeviceList()
        serials = list(DeviceManagerCLI.GetDeviceList(KCubeDCServo.DevicePrefix))
        if not serials:
            raise Exception("No KDC101 devices found.")
        self.serial = serials[0]

        self.device = KCubeDCServo.CreateKCubeDCServo(self.serial)
        self.device.Connect(self.serial)
        self.device.WaitForSettingsInitialized(200)

        config = self.device.LoadMotorConfiguration(self.serial)
        config.DeviceSettingsName = 'PRM1/M-Z8'
        config.UpdateCurrentConfiguration()

        self.device.SetSettings(self.device.MotorDeviceSettings, True, False)
        self.device.StartPolling(100)
        time.sleep(0.2)
        self.device.EnableDevice()

    def home(self, timeout=50000): 
        self.device.Home(timeout)

    def move_to(self, angle_deg, timeout=50000):
        self.device.MoveTo(Decimal(angle_deg), timeout)
        
    def is_moving(self):
        if self.device is None:
            return False
        return self.device.Status.IsInMotion
    
    def get_position(self):
        return float(str(self.device.Position).replace(',', '.'))

    def set_motion_params(self, speed, accel):
        vel = self.device.GetVelocityParams()
        vel.MaxVelocity = Decimal(speed)
        vel.Acceleration = Decimal(accel)
        self.device.SetVelocityParams(vel)

    def print_motion_params(self):
        vel = self.device.GetVelocityParams()
        print(f"Speed: {float(str(vel.MaxVelocity))} °/s")
        print(f"Accel: {float(str(vel.Acceleration))} °/s²")

    def disconnect(self):
        while self.is_moving():
            time.sleep(0.01)
        self.device.StopPolling()
        self.device.Disconnect()
