#!/bin/bash

date > hello-world.output.txt
echo last call from "$INORBIT_ROBOT_ID" >> hello-world.output.txt
echo args "$@" >> hello-world.output.txt
