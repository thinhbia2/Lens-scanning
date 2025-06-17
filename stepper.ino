#include <EEPROM.h>
#include "esp_system.h"

#define IN1 21  // Coil A+
#define IN2 20  // Coil A-
#define IN3 3  // Coil B+
#define IN4 2  // Coil B-
#define NSLEEP_PIN 10
const int EEPROM_ADDR = 0;
const int EEPROM_SIZE = 512;
const int BAUD_RATE = 115200;

int step_speed = 500;  // delay in ms
int direction = 1;     // 1 = CW, -1 = CCW
bool half_step = true;
bool running = false;
bool position_dirty = false;  // global
bool infinite_mode = false;
int steps_remaining = 0;

unsigned long last_step_time = 0;
unsigned long last_activity_time = 0;
unsigned long working_time = 10000;
int step_index = 0;
long current_position_steps = 0;

// Configurable parameters
float gear_ratio = 100.0;
float full_step_angle = 18.0;

// EEPROM structure
struct Config {
  uint32_t signature;  // magic number to detect validity
  float gear_ratio;
  float full_step_angle;
  bool half_step;
  long current_position;
  uint8_t last_step_index;
};

const uint32_t CONFIG_SIGNATURE = 0xDEADBEEF;

// 8-step half-stepping sequence
const int step_sequence[8][4] = {
  {1, 0, 0, 0},
  {1, 0, 1, 0},
  {0, 0, 1, 0},
  {0, 1, 1, 0},
  {0, 1, 0, 0},
  {0, 1, 0, 1},
  {0, 0, 0, 1},
  {1, 0, 0, 1}
};

void setup() {
	pinMode(NSLEEP_PIN, OUTPUT);
	digitalWrite(NSLEEP_PIN, LOW);
	pinMode(IN1, OUTPUT);
	digitalWrite(IN1, LOW);
	pinMode(IN2, OUTPUT);
	digitalWrite(IN2, LOW);
	pinMode(IN3, OUTPUT);
	digitalWrite(IN3, LOW);
	pinMode(IN4, OUTPUT);
	digitalWrite(IN4, LOW);

	Serial.begin(BAUD_RATE);
	EEPROM.begin(EEPROM_SIZE);
	//delay(500);
	//loadConfig();
	//digitalWrite(IN1, step_sequence[step_index][0]);
	//digitalWrite(IN2, step_sequence[step_index][1]);
	//digitalWrite(IN3, step_sequence[step_index][2]);
	//digitalWrite(IN4, step_sequence[step_index][3]);
	//delay(1000);
	
	//loadConfig();
	//esp_reset_reason_t reason = esp_reset_reason();
	//if (reason == ESP_RST_POWERON) {
	//	loadConfig();
	//}
}

void loop() {
	if (Serial.available()) {
		String command = Serial.readStringUntil('\n');
		command.trim();

		if (command.startsWith("SET")) {
			int spaceIndex1 = command.indexOf(' ', 4);
			int spaceIndex2 = command.indexOf(' ', spaceIndex1 + 1);
			int speed = command.substring(4, spaceIndex1).toInt();
			int dir = command.substring(spaceIndex1 + 1).toInt();

			step_speed = constrain(speed, 1, 10000);
			direction = (dir == 0) ? 1 : -1;

			if (spaceIndex2 > 0) {
				digitalWrite(NSLEEP_PIN, HIGH);
				steps_remaining = command.substring(spaceIndex2 + 1).toInt();
				if (steps_remaining > 0) {
					infinite_mode = false;
					running = true;
				}
			}
		} else if (command == "START") {
			digitalWrite(NSLEEP_PIN, HIGH);
			running = true;
		} else if (command == "STOP") {
			running = false;
			stopMotor();
		} else if (command == "READ") {
			loadConfig();
			Serial.print(gear_ratio);
			Serial.print(",");
			Serial.print(full_step_angle);
			Serial.print(",");
			Serial.print(half_step ? 1 : 0);
			Serial.print(",");
			Serial.println(current_position_steps);
		} else if (command == "WRITE") {
			int p1 = command.indexOf(' ', 11);
			int p2 = command.indexOf(' ', p1 + 1);

			gear_ratio = command.substring(11, p1).toFloat();
			full_step_angle = command.substring(p1 + 1, p2).toFloat();
			half_step = command.substring(p2 + 1).toInt() > 0;

			saveConfig();
		} else if (command == "ZERO") {
			current_position_steps = 0;
			saveConfig();
		}
	}

	if (running && millis() - last_step_time >= step_speed) {
		stepMotor();
		last_step_time = millis();

		if (!infinite_mode) {
			steps_remaining--;
			if (steps_remaining <= 0) {
				running = false;
				infinite_mode = true;
				stopMotor();
				Serial.println("DONE");
			}
		}
	}
	last_activity_time = millis();
	
	if (!running && millis() - last_activity_time > working_time) {
		Serial.flush();
		esp_light_sleep_start();  // Light sleep; resumes on serial
		last_activity_time = millis();  // Reset after wake
	}
}

void stepMotor() {
	step_index = (step_index + direction + 8) % 8;

	digitalWrite(IN1, step_sequence[step_index][0]);
	digitalWrite(IN2, step_sequence[step_index][1]);
	digitalWrite(IN3, step_sequence[step_index][2]);
	digitalWrite(IN4, step_sequence[step_index][3]);

	current_position_steps = (current_position_steps + direction + stepsPerRev()) % stepsPerRev();

  //position_dirty = true;
}

void stopMotor() {
	digitalWrite(NSLEEP_PIN, LOW);
	digitalWrite(IN1, LOW);
	digitalWrite(IN2, LOW);
	digitalWrite(IN3, LOW);
	digitalWrite(IN4, LOW);
	saveConfig();
	//if (position_dirty) {
	//	saveConfig();
	//	position_dirty = false;
	//}
}

long stepsPerRev() {
	float step_angle = full_step_angle / (half_step ? 2 : 1);
	return (long)((360.0 / step_angle) * gear_ratio);
}

void saveConfig() {
	//EEPROM.begin(1024);  // Allocate EEPROM space
	Config cfg = {CONFIG_SIGNATURE, gear_ratio, full_step_angle, half_step, current_position_steps};
	EEPROM.put(EEPROM_ADDR, cfg);
	EEPROM.commit();  // MUST commit on ESP32!
	//EEPROM.end();     // Optional but good practice
  
  //loadConfig();
	//Serial.print("Step #: ");
	//Serial.print(cfg.current_position);
}

void loadConfig() {
	//EEPROM.begin(1024);
	Config cfg;
	EEPROM.get(EEPROM_ADDR, cfg);
	//EEPROM.end();

	if (cfg.signature != CONFIG_SIGNATURE) {
		// First-time or corrupted EEPROM
		gear_ratio = 100.0;
		full_step_angle = 18.0;
		half_step = true;
		current_position_steps = 0;
		saveConfig();  // Save initialized values
	} else {
		gear_ratio = cfg.gear_ratio;
		full_step_angle = cfg.full_step_angle;
		half_step = cfg.half_step;
		current_position_steps = cfg.current_position;
	}
}