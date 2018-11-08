/*
 * Copyright 2018 Maciej Grela <enki@fsck.pl>
 * SPDX-License-Identifier: WTFPL
 * 
 * Very basic meter pulse output (SO) interface.
 */
 
/* 
 * The Arduino digital PIN where the S0 pulse will be present. 
 * This pin should be driven by a digital (HIGH/LOW) signal. 
 * This can be achieved by wiring the S0 output like below:
 * 
 *                 +5V
                    |
                    |
                    |
                    +----------------------- SO (+)


                    +----------------------- SO (-)
                    |
PULSE_PIN <---------+
                    |
                    |
                   +++
                   | | 100 kohm
                   | | resistor
                   +++
                    |
                    |
                    |
                   GND

 * 
 * +5V and GND are provided by the Arduino directly. The S0 wires go to the meter.
 * 
 */
#define PULSE_PIN 13

/* 
 *  This is the threshold for the pulse length. Typically the pulse is at least 50-100 ms long. 
 *  The SO (DIN 43684 / EN IEC 62053-31) standard specifies 30 ms as the minimal pulse width.
 *  Most meters generate a longer pulse. We chose 30 ms as our threshold width.
 *  
 *  References:
 *  
 *  https://www.downloads.siemens.com/download-center/Download.aspx?pos=download&fct=getasset&id1=20272 
 *  -> 30 ms as minimal pulse width
 *  https://docs-emea.rs-online.com/webdocs/0e27/0900766b80e27a08.pdf 
 *  -> generates 100 ms pulse
 *  https://library.e.abb.com/public/6e8aabe17e9880a4c1257084004c49dd/2CDC512038D0201.pdf 
 *  -> generates 100 ms pulse
 *  https://docs.google.com/viewer?a=v&pid=sites&srcid=ZGVmYXVsdGRvbWFpbnxudGE4MTMwcDFzbWFydG1ldGVyfGd4OmYzMjc0ZTFjMzFkYzYwMw 
 *  -> Mentions the standard and 30 ms as the minimum pulse width
 */
#define PULSE_WIDTH_THRESHOLD 30

void setup() {
  pinMode(PULSE_PIN, INPUT);
  
  Serial.begin(115200);
}

void loop() {
  
  // Wait for pulse rising edge
  while (digitalRead(PULSE_PIN) == LOW) {}

  unsigned long pulse_start = millis();

  // Wait for pulse falling edge
  while (digitalRead(PULSE_PIN) == HIGH) {}
  
  unsigned long pulse_end = millis();

  if (pulse_end - pulse_start > PULSE_WIDTH_THRESHOLD) {
    Serial.println("pulse");
  }
}
