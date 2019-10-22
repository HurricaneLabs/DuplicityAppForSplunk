#!/bin/bash

unset LD_LIBRARY_PATH
unset PYTHONPATH

cd $( dirname "${BASH_SOURCE[0]}" )
/usr/bin/python ./duplicity-input.py
