/*
 * Copyright 2020 Maciej Grela <enki@fsck.pl>
 * SPDX-License-Identifier: WTFPL
 *
 * Very basic pulse frequency measurement code.
 * Useful for digital anemometers which provide a pulse output.
 */

/*
 * The circuit used to connect a pulse-type windspeed sensor will                   
 * depend on the type of the switch in the sensor as well as the 
 * configured edge type. As an example, for a sensor where the 
 * switch is normally CLOSED (that is the pulses OPEN the switch) 
 * the following circuit can be used. With a N/C windspeed sensor
 * and the circuit below the code needs to be set to detect a raising
 * signal edge on the pulsePin (that is LOW -> HIGH).
 * 
 *                 +5V
                    ^
                    |
                    |
                    |
                   +++
                   | |
                   | |
                   +++
                    |
pulsePin <----------+--------------------->
                                            N/C windspeed sensor
                    +--------------------->
                    |
                    v
                   GND

 */

// Print debug information to serial port when uncommented
//#define DEBUG

const int pulsePin = 2;

/*
 * A raising edge (LOW -> HIGH transition) in pulsePin is treated as pulse begin.
 * Please see the reference of the pulseIn() Arduino function for the description.
 * Reference: https://www.arduino.cc/reference/en/language/functions/advanced-io/pulsein/
 */
const int pulseEdge = HIGH; 

// minimal pulse width in microseconds, pulses shorter than this are rejected as glitches
const int pulseMinWidth = 100; 

// count pulses for 10 seconds and calculate average frequency for that period
const float windowTime = 10; 

unsigned long windowBegin = 0;
unsigned int pulseCount = 0;

void setup() {
  pinMode(pulsePin, INPUT);

  Serial.begin(115200);

  #ifdef DEBUG
  Serial.print("$init pin=");
  Serial.print(pulsePin);
  Serial.print(" edge=");
  Serial.print(pulseEdge);
  Serial.print(" min_width=");
  Serial.print(pulseMinWidth);
  Serial.print("us windowTime=");
  Serial.print(windowTime);
  Serial.println("s");
  #endif
  
  windowBegin = millis();
}


void loop() {

  unsigned long pulseLength = pulseInLong(pulsePin, pulseEdge);
  if ( pulseLength > pulseMinWidth ) { pulseCount++; }

  unsigned long T = millis();
  if ( T - windowBegin >= windowTime * 1e3 ) {
    unsigned long windowLength = T - windowBegin;

    #ifdef DEBUG
    Serial.print("$debug ");
    Serial.print("window=");
    Serial.print(windowLength);
    Serial.print("ms pulses=");
    Serial.println(pulseCount);
    #endif
    
    Serial.print( pulseCount / (windowLength/(float)1e3) );
    Serial.println(" Hz");
    
    pulseCount = 0;
    windowBegin = millis();
  }
}
