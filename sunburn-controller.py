#!/usr/bin/env python3

# Sunburn project - Main control software
#
# This project was HIP energy research for assessing if solar panel energy could be
# used to operate a computer with minimal battery support. That is, using the available energy
# instead of storing it. This is accomplished through measurements of both supplied solar panel
# energy and energy consumption of the attached computer.

# The computer slaved to this system would operate based on instructions issued by this controller.
# In short the control included sending following instructions to client software:
#   * Turning the computer on and off
#   * (de)limiting the number of cores available to tasks
#   * (de)limiting the percentage of each core available to the tasks
#
#
# Short system component overview:
#   electrics -> measurement subsystem -> control -> network subsystem -> slaved computer.



import time
import power as pwr
import udpCommunication as udpcomms
import fcntl
import os
import sys


# Constants

#Use debug printouts
DEBUG = 1

# Number of cores
CORES = 4

# Minimum power of system. Used as activation limit.
MIN_POWER = 18
# Deadzone value used deciding whether to change number of used cores or not.
# Used to reduce unnecessary changes.
CHANGE_DEADZONE = 1.5


# Short and "long" average ranges
# Short should be kept as small as possible, without introducing excessive fluctuations.
SHORT_AVG = 1
LONG_AVG = 6

# Interval limit for performing adjustments. That is, how many rounds of measurements are done before PID adjustment.
# This has an effect on PID/system responsiveness.
ADJUST_INTERVAL = 1

# Computer on and off round limits
OFF_LIMIT = 2
ON_LIMIT = 2

# PID derivative time
DT = 4

# Modes
MODE_AUTO = 0
MODE_LIMIT_TEST = 1
MODE_PWR_TEST = 2


def real_cpu_use():
  """ Calculates real CPU use. Basically measured CPU usage times the multiplier based on
  number of active cores.
  """
  return core_conversion_multipliers[processor_limits[1]] * cpu_use

def readFloat():
"""Read float value input from user. Returns value or None"""
  val = input().lower()
  if val == "":
    pass
  else:
     try:
       return float(val)
     except ValueError:
       print("Given value is not a valid number")
       return None

def interface(mode, pid, processor_limits, manual_target):
    """Rudimentary user interface for adjusting the system settings. Arguments: interface(mode, pid, processor_limits, manual_target) returns updated values for these."""
  
  print("Input command: (M)ode select/adjust - (P)ID adjust - Empty input cancels")
  key = input().lower()
  if key == "m":
    if not mode:
      print("Enter which mode? Manual (p)ower level, manual CPU (l)imit or (a)utomatic mode (default)?")
      key = input().lower()
      if key == "l":
        # Enable manual CPU limit mode
        mode = MODE_LIMIT_TEST
      elif key == "p":
        # Enable manual power entry mode
        mode = MODE_PWR_TEST
      elif key == "a":
        # Automatic mode
        mode = MODE_AUTO
  # PID value adjustment
  elif key == "p":
    val = None      
    while(val == None):
      print("Enter new proportional value (" + str(kp) + ")")
      val = readFloat()
    pid[0] = val
    val = None
    while(val == None):
      print("Enter new integral value (" + str(ki) + ")")
      val = readFloat()
    pid[1] = val
    val = None
    while(val == None):
      print("Enter new derivative value (" + str(kd) + ")")
      val = readFloat()
    pid[2] = val
    print("New values (P, I, D): " + str(pid[0]) + ", " + str(pid[1])+ ", " + str(pid[2]) )
      

  # Mode selections: 
  # 1 Manual cpu/core limits
  #    Bypasses all the core/cpu adjustments
  # 2 Manual power target mode
  #    Replaces the solar system power value with given one

  # Assess entered mode and collect related data from user.
  if mode == MODE_LIMIT_TEST:
    print("Input new limit values.")
    i = None
    while(i == None):
      print("Enter CPU limit (" + str(processor_limits[0]) + ")")
      i = readFloat()
    if i > 100:
      i = 100
    elif i < 7:
      i = 7
     processor_limits[0] = i
     i = None
    while(i == None):
      print("Enter core limit (" + str(processor_limits[1]) + ")")
      i = readFloat()
    if i > 4:
      i = 4
    elif i < 1:
      i = 1
    processor_limits[1] = int(i)
    print("New values (CPU, cores): " + str(processor_limits[0])+ ", " + str(processor_limits[1]))
    
  elif mode == MODE_PWR_TEST:
    print("Input new power.")
    i = None
    while(i == None):
      print("Enter new power target (" + str(manual_target) + ")")
      i = readFloat()
    if i < 1:
      i = 0
    
    
  # Return changed state
  return mode, pid, processor_limits, manual_target

def adjust(target, measured, integral, pid, previous_error):
  """PID. Calculates an adjustment value based on the given target and current measured value.
  Arguments: target value, measured value, integral, pid values in array
  """
  
  # Normal PID calculations
  error = target - measured
  new_integral = integral + error*DT
  # Limit the integral min and max 
  if new_integral > 10:
    new_integral = 10
  elif new_integral < -10:
    new_integral = -10
  derivative = (error - previous_error)/DT
  adjustment = pid[0] * error / 10 + pid[1] * integral / 10 + pid[2] * derivative / 10
  
  if DEBUG:
    print("** PID values:")
    print("** TGT: " + str(target) + " - CURRENT: " + str(measured))
    print("** Error: " + str(error) + " - Derivative: " + str(derivative) + " - Integral: " +  str(integral))
    print(adjustment)
    print(adjustment)
  
  return adjustment, new_integral, error

def average(data):
  """Average given array"""
  return sum(data) / float(len(data))

    

#************************************
#************************************
    
def main():    
  """Main function. Init system and start measurement/adjustment/control cycle
Number of measurement rounds is defined by value of ADJUST_INTERVAL. Default
value is 1, which translates to cycle of two measurements per adjustment.

While running, the PID values can be adjusted via interface.
  """

  #Initial intervals and power control
  adjust_interval = 0
  powered = 0
  power_counter = 0
  
  # Mode of the system
  # Mode 0: Automatic (Default)
  # Mode 1: Test mode 1 - Manually set CPU/Core limits
  # Mode 2: Test mode 2 - Manually set power level target
  mode = MODE_AUTO

  #Power budget value
  budget = 0

  # Initial values for measurements

  power_target = 0
  usage_power = [0]
  usage_power_avg = [0]

  supply_power = [0]
  supply_power_avg = [0]

  cpu_use = 0
  
  # PID values
  pid[19, 0.5, 1]
  
  integral = 0
  previous_error = 0
  
  # Real cpu usage conversion values. These need to be changed if target system has more or 
  # less than 4 cores.
  core_conversion_multipliers = [0, 4.0, 2.0, 1.34, 1.0]

  # Preset core power values in watts for Intel Core I3 4330. These can be adjusted to match used 
  # processor
  core_limits = [16, 31.0, 33.4, 47, 51.5]
  
  # Processor limits = [cpu use limit in pct, number of active cores]
  processor_limits[7,0]
  
  #Power target value in manual mode
  manual_power_target = 0




  
  # Init keypress detection
  fl = fcntl.fcntl(sys.stdin.fileno(), fcntl.F_GETFL)
  fcntl.fcntl(sys.stdin.fileno(), fcntl.F_SETFL, os.O_NONBLOCK)
      
  # Init the power system and ensure the power is off.
  pwr.init()
  pwr.power_off()

  print("System started with default values: Press enter for settings")

    
  while(1):
    #Detect keypress, activate settings
    try:
      stdin = sys.stdin.read()
      if "\n" in stdin or "\r" in stdin:
        mode, pid, processor_limits, manual_target = interface(mode, pid, processor_limits, manual_target)
    except IOError:
      pass


    #Collect CPU data from client over network.
    msg = udpcomms.wait_msg()
    if msg == None:
       cpu_use = 0
    else:
     data = msg.split(":")
     if data[0] == "status" :
        try:
          cpu_use = float(data[1]) 
        except ValueError:
          print("Received message contained invalid data")
          cpu_use = 0
          
          
          
    # Run measurement routine
    pwr.measure()
    
    # Retrieve the measured values from power subsystem.
    # Result should be a namedtuple in form of:
    # measurements(usage_voltage, usage_current, usage_power, supply_voltage, supply_current, supply_power)

    measurements = pwr.get_measurements_tuple()
    
    # To smooth sudden spikes out, the power values are based on average over several
    # measurements. The short term values is stored in supply_power and usage_power.
    # The long term values in supply_power_average and usage_power_average.
    # All of these are averages, but short term window is so small that this is basically
    # one measurement, thus the naming.
    
    #Log power from supply if system is not in manual control mode 2. Otherwise use the manually set power target
    if mode < MODE_PWR_TEST:
      supply_power.append(measurement.supply_power)
      supply_power_avg.append(measurement.supply_power)
    else:
      supply_power.append(manual_power_target)
      supply_power_avg.append(manual_power_target)
    
    # Drop oldest values if the averaging window is full.
    if len(supply_power) > SHORT_AVG:
      supply_power.pop(0)
      usage_power.pop(0)
    if len(supply_power_avg) > LONG_AVG:
      supply_power_avg.pop(0)
      usage_power_avg.pop(0)
    
    #Averages used in adjustment
    power_target = average(supply_power)
    power = average(usage_power)
    
    
    # Adjustment routine
    # This compares the known core power values against the measured values and adjusts the
    # number of cores as needed. This greatly enhances the adaptation speed to sudden
    # changes in power supply.
    
    # Approximate a new value of cpu limit from following formula: 
    # (Target - Core lower limit) / (Core upper limit - core lower limit) = cpu limit
    # or
    # Core power demand / Core power range = cpu limit
    # 
    # This is by no means accurate, but sets the cpu use limit closer to target, allowing
    # the PID to get back into play faster
    
    if mode != MODE_LIMIT_TEST and powered:

    # If adjustment interval is reached, adjust.
      if adjust_interval > ADJUST_INTERVAL:
        adjust_interval = 0
        # Calculate and add adjustment to current processor limits
        new_limit, integral, previous_error = adjust(power_target, power, integral, pid, previous_error)
        processor_limits[0] += new_limit

        
        #Change upward, increase number of used cores and reduce cpu usage.
        if power_target > core_limits[processor_limits[1]]:
           processor_limits[1] += 1
           if processor_limits[1] > CORES:
              processor_limits[1] = CORES
           else:
              
              upper = core_limits[processor_limits[1]]
              lower = core_limits[processor_limits[1] - 1]

              processor_limits[0] = int(((power_target - lower) / (upper - lower)) * 100)
              
        # Change downward, reduce number of cores and increase cpu usage.
        elif processor_limits[1] > 1:
        
          # Allow some leeway before changing number of cores. This prevents unnecessary jumps
          # if there operating power is near the limits of the power ratings of two cores.
          
          if power_target < (core_limits[processor_limits[1] - 1] - CHANGE_DEADZONE):
            # Decrease number of cores, perform sanity checks
            processor_limits[1] -= 1
            if DEBUG:
              print("** Core limited - core limit now at : " + str(processor_limits[1]))
            if processor_limits[1] < 1:
              processor_limits[1] = 1
            else: 

            # Calculate value for cpu limit based on number of active cores
            # Caveat: When going down, the max power of cores 1 & 2 and 3 & 4 are
            # within few watts due to HyperThreading. Thus the jump from comparing
            # idle to comparing core 2.
            
              if processor_limits[1] < 2:
                upper = core_limits[1]
                lower = core_limits[0]                
              elif processor_limits[1] < 3:
                upper = core_limits[2]
                lower = core_limits[0]
              else:
                upper = core_limits[3]
                lower = core_limits[2]
                
              processor_limits[0] = int(((power_target - lower) / (upper - lower)) * 100)
              
              # If the current integral is aggressive, reduce it slightly to make life of PID easier.
              if integral > 5:
                integral -= 1

        #Sanity checks, cpu limit of less than 7 % unachiavable due to CPUlimit limitations on clientside.
        if processor_limits[0] > 100:
           processor_limits[0] = 100
        elif processor_limits[0] < 7:
           processor_limits[0] = 7


    # Computer state control, used if the system is not in manual limit mode.
    # This also ensures that the computer is turned on in mode 1.
    if mode != MODE_LIMIT_TEST:
      # Shutdown-Powerup check
      # Compare current power to minimum power and increment/decrement counter.
      # If counter exceeds limits, shutdown/startup client.
      
      if power_target < MIN_POWER and powered:
        power_counter -= 1
      else:
        power_counter = 0
      if power_target > MIN_POWER and not powered:
        power_counter += 1
      else:
        power_counter = 0
    
      if power_counter > ON_LIMIT:
        pwr.power_on()
        processor_limits[1] = 1
        powered = 1
        
      elif power_counter < OFF_LIMIT:
        pwr.power_off()
        processor_limits[1] = 0
        udpcomms.send_msg("shutdown:")
        powered = 0
    elif mode == MODE_LIMIT_TEST and not powered:
	pwr.power_on()
	powered = 1

    # Change adjust interval and ensure that the value stays sane when no adjustment is done to the system.
    if adjust_interval > ADJUST_INTERVAL:
      adjust_interval = 0
    adjust_interval += 1  
    
    #Issue commands to client
    if powered:
      udpcomms.send_msg("control:" + str(processor_limits[1]) + ":" + str(processor_limits[0]))
      #Poll computer for status
      udpcomms.send_msg("status:")
    
    # Rough estimate of system accuracy in long run. 
    budget += power_target - power
    if DEBUG:
      print("\n\n Current Power Budget: " + str(budget) + "\n")    

      
if __name__ == "__main__":
  main()
  
  
