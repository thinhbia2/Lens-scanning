import clr
import os
import time
import System
from System import Decimal
import inspect

kinesis_path = r"C:\Program Files\Thorlabs\Kinesis"
os.environ["PATH"] += os.pathsep + kinesis_path

# Load DLLs
clr.AddReference(os.path.join(kinesis_path, "Thorlabs.MotionControl.DeviceManagerCLI.dll"))
clr.AddReference(os.path.join(kinesis_path, "Thorlabs.MotionControl.GenericMotorCLI.dll"))
clr.AddReference(os.path.join(kinesis_path, "Thorlabs.MotionControl.KCube.DCServoCLI.dll"))
clr.AddReference(os.path.join(kinesis_path, "Thorlabs.MotionControl.KCube.InertialMotorCLI.dll"))

from Thorlabs.MotionControl.DeviceManagerCLI import DeviceManagerCLI
from Thorlabs.MotionControl.KCube.DCServoCLI import KCubeDCServo
from Thorlabs.MotionControl.KCube.InertialMotorCLI import *
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

class KIM001Controller:
    def __init__(self):
        self.device = None
        self.serial = None

    def connect(self):
        DeviceManagerCLI.BuildDeviceList()

        serials = DeviceManagerCLI.GetDeviceList()
        if not serials:
            raise Exception("No KIM001 devices found.")
        self.serial = serials[0]

        self.device = KCubeInertialMotor.CreateKCubeInertialMotor(self.serial)
        self.device.Connect(self.serial)
        self.device.WaitForSettingsInitialized(200)

        device_info = self.device.GetDeviceInfo()
        #print(device_info.Description)
        config = self.device.GetInertialMotorConfiguration(self.serial)
        device_settings = ThorlabsInertialMotorSettings.GetSettings(config)
        self.chan1 = InertialMotorStatus.MotorChannels.Channel1 
        #print(device_settings.Drive.Channel(self.chan1).StepRate)
        #print(device_settings.Drive.Channel(self.chan1).StepAcceleration)
        device_settings.Drive.Channel(self.chan1).StepRate = 500
        device_settings.Drive.Channel(self.chan1).StepAcceleration = 100000
        self.device.SetSettings(device_settings, True, True)
        self.device.SetPositionAs(self.chan1, 0)
        
        self.device.StartPolling(100)
        self.device.EnableDevice()

        #self.device.SetStepSize(Decimal(50))
        #self.device.StartMove(InertialMotorMoveDirection.Increase)
        #channel = self.device.GetChannel(self.chan1)
        #channel.Jog(InertialMotorJogDirection.Increase)
        #print(InertialMotorJogDirection)
        #self.device.Jog(self.chan1, InertialMotorJogDirection.Forward)
        #self.device.SetSettings(device_settings, True, True)

        #config.DeviceSettingsName = 'PIA13'
        #config.UpdateCurrentConfiguration()

        #self.device.SetSettings(self.device.MotorDeviceSettings, True, False)
        #self.device.StartPolling(100)
        #time.sleep(0.2)
        #self.device.EnableDevice()

    def home(self, timeout=50000): 
        self.device.Home(timeout)

    def move_to(self, step, timeout=50000):
        new_pos = Decimal(step)
        self.device.MoveTo(self.chan1, new_pos, timeout)

    def move_relative(self, step, timeout=50000):
        new_pos = int(step)
        self.device.MoveBy(self.chan1, new_pos, timeout)        
        
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
        #while self.is_moving():
        #    time.sleep(0.01)
        self.device.StopPolling()
        self.device.Disconnect()
