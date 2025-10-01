#include <EEPROM.h>
#include "esp_system.h"
#include <math.h>  // for lround()

// Motor 0 pins
#define M0_IN1 21
#define M0_IN2 20
#define M0_IN3 10
#define M0_IN4 9
#define M0_NSLEEP_PIN 0

// Motor 1 pins
#define M1_IN1  7
#define M1_IN2  8
#define M1_IN3  6
#define M1_IN4  5
#define M1_NSLEEP_PIN 1

// Motor 3 pins
#define M2_IN1 7
#define M2_IN2 8
#define M2_IN3 6
#define M2_IN4 5
#define M2_NSLEEP_PIN 3

// Motor 4 pins
#define M3_IN1 21
#define M3_IN2 20
#define M3_IN3 10
#define M3_IN4 9
#define M3_NSLEEP_PIN 2

const int EEPROM_SIZE = 1024;
const int BAUD_RATE = 115200;

//int step_speed = 500;  // delay in ms
//int direction = 1;     // 1 = CW, -1 = CCW
//bool half_step = true;
//bool running = false;
//bool position_dirty = false;  // global
//bool infinite_mode = false;
//int steps_remaining = 0;
//
//unsigned long last_step_time = 0;
//unsigned long last_activity_time = 0;
//unsigned long working_time = 10000;
//int step_index = 0;
//long current_position_steps = 0;
//
//// Configurable parameters
//float gear_ratio = 100;
//float full_step_angle = 18.0;

// EEPROM structure
struct Config {
  uint32_t signature;  // magic number to detect validity
  float gear_ratio;
  float full_step_angle;
  bool half_step;
  long current_position;
  uint8_t last_step_index;
};

struct Motor {
  // Pins
  int in1, in2, in3, in4, nsleep;
  // Runtime vars
  int step_speed;
  int direction;
  bool running;
  bool infinite_mode;
  int steps_remaining;
  int step_index;
  long current_position_steps;
  // Config
  float gear_ratio;
  float full_step_angle;
  bool half_step;
  // Timing
  unsigned long last_step_time;
};

Motor motors[4];
const int EEPROM_ADDR[4] = {
  0,
  sizeof(Config),
  2 * sizeof(Config),
  3 * sizeof(Config)
};

const uint32_t CONFIG_SIGNATURE = 0xDEADBEEF;

// 8-step half-stepping sequence
const int step_sequence_8[8][4] = {
  {1, 0, 0, 0},
  {1, 0, 1, 0},
  {0, 0, 1, 0},
  {0, 1, 1, 0},
  {0, 1, 0, 0},
  {0, 1, 0, 1},
  {0, 0, 0, 1},
  {1, 0, 0, 1}
};

const int step_sequence_4[4][4] = {
  {1,0,1,0},
  {0,1,1,0},
  {0,1,0,1},
  {1,0,0,1}
};


// ---------------- Function prototypes ----------------
void setupMotor(int id, int in1, int in2, int in3, int in4, int nsleep);
void loadConfig(int id);
void saveConfig(int id);
long stepsPerRev(int id);
void stepMotor(int id);
void stopMotor(int id);

void setup() {
	setupMotor(0, M0_IN1, M0_IN2, M0_IN3, M0_IN4, M0_NSLEEP_PIN);
	setupMotor(1, M1_IN1, M1_IN2, M1_IN3, M1_IN4, M1_NSLEEP_PIN);
	setupMotor(2, M2_IN1, M2_IN2, M2_IN3, M2_IN4, M2_NSLEEP_PIN);
	setupMotor(3, M3_IN1, M3_IN2, M3_IN3, M3_IN4, M3_NSLEEP_PIN);

	Serial.begin(BAUD_RATE);
	EEPROM.begin(EEPROM_SIZE);
}

void loop() {
	// ----------- Serial Command Handling -----------
	if (Serial.available()) {
		String command = Serial.readStringUntil('\n');
		command.trim();

		if (command.startsWith("SET")) {
			// SET <id> <speed> <dir> [steps]
			int id, speed, dir, steps;
			int args = sscanf(command.c_str(), "SET %d %d %d %d", &id, &speed, &dir, &steps);
			if (id >= 0 && id < 4) {
				motors[id].step_speed = constrain(speed, 1, 10000);
				motors[id].direction = (dir == 0) ? 1 : -1;
				digitalWrite(motors[id].nsleep, HIGH);
				if (args == 4) {
					motors[id].steps_remaining = steps;
					motors[id].infinite_mode = false;
					motors[id].running = true;
				} else {
					motors[id].infinite_mode = true;
				}
			}

		} else if (command.startsWith("START")) {
			int id;
			if (sscanf(command.c_str(), "START %d", &id) == 1 && id >= 0 && id < 4) {
				digitalWrite(motors[id].nsleep, HIGH);
				motors[id].running = true;
			}

		} else if (command.startsWith("STOP")) {
			int id;
			if (sscanf(command.c_str(), "STOP %d", &id) == 1 && id >= 0 && id < 4) {
				motors[id].running = false;
				stopMotor(id);
			}

		} else if (command.startsWith("READ")) {
			int id;
			if (sscanf(command.c_str(), "READ %d", &id) == 1 && id >= 0 && id < 4) {
				loadConfig(id);
				Serial.print(motors[id].gear_ratio);
				Serial.print(",");
				Serial.print(motors[id].full_step_angle);
				Serial.print(",");
				Serial.print(motors[id].half_step ? 1 : 0);
				Serial.print(",");
				Serial.println(motors[id].current_position_steps);
			}

		} else if (command.startsWith("WRITE")) {
			int id, h;
			float g, s;
			if (sscanf(command.c_str(), "WRITE %d %f %f %d", &id, &g, &s, &h) == 4 && id >= 0 && id < 4) {
				motors[id].gear_ratio = g;
				motors[id].full_step_angle = s;
				motors[id].half_step = (h > 0);
				saveConfig(id);
			}

		} else if (command.startsWith("ZERO")) {
			int id;
			if (sscanf(command.c_str(), "ZERO %d", &id) == 1 && id >= 0 && id < 4) {
				motors[id].current_position_steps = 0;
				saveConfig(id);
			}
		}
	}

	// ----------- Motor Stepping -----------
	for (int id = 0; id < 4; id++) {
		if (motors[id].running && millis() - motors[id].last_step_time >= motors[id].step_speed) {
			stepMotor(id);
			motors[id].last_step_time = millis();

			if (!motors[id].infinite_mode) {
				motors[id].steps_remaining--;
				if (motors[id].steps_remaining <= 0) {
					motors[id].running = false;
					motors[id].infinite_mode = true;
					stopMotor(id);
					Serial.print("DONE ");
					Serial.print(id);
					Serial.print(" ");
					Serial.println(motors[id].current_position_steps);
				}
			}
		}
	}
}

// ---------------- Function Definitions ----------------
void setupMotor(int id, int in1, int in2, int in3, int in4, int nsleep) {
	motors[id].in1 = in1;
	motors[id].in2 = in2;
	motors[id].in3 = in3;
	motors[id].in4 = in4;
	motors[id].nsleep = nsleep;

	pinMode(in1, OUTPUT);
	pinMode(in2, OUTPUT);
	pinMode(in3, OUTPUT);
	pinMode(in4, OUTPUT);
	pinMode(nsleep, OUTPUT);

	digitalWrite(in1, LOW);
	digitalWrite(in2, LOW);
	digitalWrite(in3, LOW);
	digitalWrite(in4, LOW);
	digitalWrite(nsleep, LOW);

	motors[id].step_speed = 500;
	motors[id].direction = 1;
	motors[id].running = false;
	motors[id].infinite_mode = false;
	motors[id].steps_remaining = 0;
	motors[id].step_index = 0;
	motors[id].current_position_steps = 0;
	motors[id].last_step_time = 0;

	loadConfig(id);
}

void loadConfig(int id) {
	Config cfg;
	EEPROM.get(EEPROM_ADDR[id], cfg);
	if (cfg.signature != CONFIG_SIGNATURE) {
		motors[id].gear_ratio = 100.0;
		motors[id].full_step_angle = 18.0;
		motors[id].half_step = true;
		motors[id].current_position_steps = 0;
		saveConfig(id);
	} else {
		motors[id].gear_ratio = cfg.gear_ratio;
		motors[id].full_step_angle = cfg.full_step_angle;
		motors[id].half_step = cfg.half_step;
		motors[id].current_position_steps = cfg.current_position;
	}
}

void saveConfig(int id) {
	Config cfg = {CONFIG_SIGNATURE, motors[id].gear_ratio, motors[id].full_step_angle,
				motors[id].half_step, motors[id].current_position_steps};
	EEPROM.put(EEPROM_ADDR[id], cfg);
	EEPROM.commit();
}

long stepsPerRev(int id) {
	//float step_angle = motors[id].full_step_angle / (motors[id].half_step ? 2 : 1);
	//return lround((360.0 / step_angle) * motors[id].gear_ratio);
	float step_angle = motors[id].full_step_angle; // no /2 for half-step
	return lround((360.0 / step_angle) * motors[id].gear_ratio);
}

void stepMotor(int id) {
	if(motors[id].half_step){
		motors[id].step_index = (motors[id].step_index + motors[id].direction + 8) % 8;
		digitalWrite(motors[id].in1, step_sequence_8[motors[id].step_index][0]);
		digitalWrite(motors[id].in2, step_sequence_8[motors[id].step_index][1]);
		digitalWrite(motors[id].in3, step_sequence_8[motors[id].step_index][2]);
		digitalWrite(motors[id].in4, step_sequence_8[motors[id].step_index][3]);
	}
	else {
		motors[id].step_index = (motors[id].step_index + motors[id].direction + 4) % 4;
		digitalWrite(motors[id].in1, step_sequence_4[motors[id].step_index][0]);
		digitalWrite(motors[id].in2, step_sequence_4[motors[id].step_index][1]);
		digitalWrite(motors[id].in3, step_sequence_4[motors[id].step_index][2]);
		digitalWrite(motors[id].in4, step_sequence_4[motors[id].step_index][3]);
	}
	motors[id].current_position_steps =
	  (motors[id].current_position_steps + motors[id].direction + stepsPerRev(id)) % stepsPerRev(id);
}

void stopMotor(int id) {
	digitalWrite(motors[id].nsleep, LOW);
	digitalWrite(motors[id].in1, LOW);
	digitalWrite(motors[id].in2, LOW);
	digitalWrite(motors[id].in3, LOW);
	digitalWrite(motors[id].in4, LOW);
	saveConfig(id);
}
