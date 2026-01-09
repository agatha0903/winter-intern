#!/usr/bin/env python
# Copyright (c) 2020-2022, Universal Robots A/S,
# All rights reserved.
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#    * Redistributions of source code must retain the above copyright
#      notice, this list of conditions and the following disclaimer.
#    * Redistributions in binary form must reproduce the above copyright
#      notice, this list of conditions and the following disclaimer in the
#      documentation and/or other materials provided with the distribution.
#    * Neither the name of the Universal Robots A/S nor the names of its
#      contributors may be used to endorse or promote products derived
#      from this software without specific prior written permission.
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL UNIVERSAL ROBOTS A/S BE LIABLE FOR ANY
# DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
# ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import argparse
import logging
import sys

sys.path.append("../..")
import rtde.rtde as rtde
import rtde.rtde_config as rtde_config
import rtde.csv_writer as csv_writer
import rtde.csv_binary_writer as csv_binary_writer
import datetime
import time
from rtde_control import RTDEControlInterface as RTDEControl
from rtde_receive import RTDEReceiveInterface as RTDEReceive
# parameters
parser = argparse.ArgumentParser()
parser.add_argument(
    "--host", default="192.168.10.11", help="name of host to connect to (localhost)"
)
parser.add_argument("--port", type=int, default=30004, help="port number (30004)")
parser.add_argument(
    "--samples", type=int, default=0, help="number of samples to record"
)
parser.add_argument(
    # "--frequency", type=int, default=120, help="the sampling frequency in Herz"
    "--frequency", type=int, default=100, help="the sampling frequency in Herz"

)
parser.add_argument(
    "--config",
    default="record_configuration.xml",
    help="data configuration file to use (record_configuration.xml)",
)

parser.add_argument(
    "--output",
    default="robot_data.csv",
    help="data output file to write to (robot_data.csv)",
)
parser.add_argument("--verbose", help="increase output verbosity", action="store_true")
parser.add_argument(
    "--buffered",
    help="Use buffered receive which doesn't skip data",
    action="store_true",
)
parser.add_argument(
    "--binary", help="save the data in binary format", action="store_true"
)
args = parser.parse_args()

if args.verbose:
    logging.basicConfig(level=logging.INFO)

# Initialize RTDE interfaces
rtde_c = RTDEControl(args.host)
rtde_r = RTDEReceive(args.host)
current_tcp_pose = rtde_r.getActualTCPPose()
# print(f"Current TCP Position: x={current_tcp_pose[0]}, y={current_tcp_pose[1]}, z={current_tcp_pose[2]}")
# print(f"Current TCP Orientation: rx={current_tcp_pose[3]}, ry={current_tcp_pose[4]}, rz={current_tcp_pose[5]}")

num_positions = 100
points = []
x = current_tcp_pose[0]
y = current_tcp_pose[1]
z = current_tcp_pose[2]
rx = current_tcp_pose[3]
ry = current_tcp_pose[4]
rz = current_tcp_pose[5]

# sample 1st
# x = -0.0953
# y = -0.4155
# z = 0.37
# rx = 0
# ry = 3.09
# rz = 0

# sample 2nd
# x = -0.12
# y = -0.4
# z = 0.372
# rx = 0
# ry = 3.14
# rz = 0

# sample 3rd
# x = -0.1
# y = -0.43
# z = 0.37
# rx = 0.022
# ry = 3.066
# rz = -0.114

# sample 4th
# x = -0.1
# y = -0.42
# z = 0.37
# rx = 0.022
# ry = 3.066
# rz = -0.114

pointt = [x, y, z, rx, ry, rz]
for i in range(1, num_positions+1):
    y = y - 0.0001
    pointt = [x, y, z, rx, ry, rz]
    points.append(pointt)

# Define velocities and accelerations in mm/s and mm/s^2
velocities_mm = []
accelerations_mm2 = []
# Pause time after reaching each point (in seconds)
pause_times = []

for i in range(1, num_positions+1):
    velocities_mm.append(10)
    accelerations_mm2.append(10)
    pause_times.append(0.2)

# Convert units to m/s and m/s² for the robot API
velocities_m = [v * 0.001 for v in velocities_mm]
accelerations_m = [a * 0.001 for a in accelerations_mm2]




conf = rtde_config.ConfigFile(args.config)
output_names, output_types = conf.get_recipe("out")

con = rtde.RTDE(args.host, args.port)
con.connect()

# get controller version
con.get_controller_version()

# setup recipes
if not con.send_output_setup(output_names, output_types, frequency=args.frequency):
    logging.error("Unable to configure output")
    sys.exit()

# start data synchronization
if not con.send_start():
    logging.error("Unable to start synchronization")
    sys.exit()

writeModes = "wb" if args.binary else "w"


csv_file = 'robot_data_{}.csv'.format(datetime.datetime.now().strftime('%Y-%m-%d %H_%M_%S.%f')[:-3])
with open(csv_file, 'w') as csvfile:
    # writer = None

    # if args.binary:
    #     writer = csv_binary_writer.CSVBinaryWriter(csvfile, output_names, output_types)
    # else:
    #     writer = csv_writer.CSVWriter(csvfile, output_names, output_types)
    #
    # writer.writeheader()

    i = 1
    keep_running = True
    for j, point in enumerate(points):
        print(f"Moving to point {j + 1}...")
        rtde_c.moveL(point, velocities_m[j], accelerations_m[j])
        print(f"Arrived at point {j + 1}. Pausing {pause_times[j]} sec...")

        # time.sleep(pause_times[j])
        pause_start = time.time()
        while time.time() - pause_start < pause_times[j]:
            if args.samples > 0 and i >= args.samples:
                keep_running = False


            try:
                if args.buffered:
                    state = con.receive_buffered(args.binary)
                else:
                    state = con.receive(args.binary)
                if state is not None:
                    # writer.writerow(state)
                    # print(len(state.actual_TCP_pose))
                    tims = [datetime.datetime.now().strftime('%Y-%m-%d %H_%M_%S.%f')[:-3]]
                    data_info = tims + state.actual_TCP_pose + state.target_TCP_pose
                    row = ' '.join(map(str, data_info)) + '\n'  # Convert each element to string and join with space
                    csvfile.write(row)
                    i += 1
            except rtde.RTDEException:
                con.disconnect()
                rtde_c.stopScript()
                sys.exit()

            except KeyboardInterrupt:
                keep_running = False
            # time.sleep(1.0 / args.frequency)  # Control sampling rate to 100 Hz
        if not keep_running:
            break

        if j == len(points) - 1:
            print(f"Reached final point {j + 1}. Stopping execution.")
            break
    # print(f"Reached final point {j + 1}. Stopping execution.")
    # break
        # except rtde.RTDEException:
        #     con.disconnect()
        #     sys.exit()


sys.stdout.write("\rComplete!            \n")

con.send_pause()
con.disconnect()
rtde_c.stopScript()