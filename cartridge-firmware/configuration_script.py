Import("env")

if env.IsIntegrationDump():
   Return()


import os
import shutil

precompile_script_success: bool = False
def pre(*_):
    # runs pre compilation but post project configuration
    print('Custom pre compilation script running now')
    global precompile_script_success
    precompile_script_success = True

def post(source, target, env):
    # runs after the .hex firmware has been generated
    if not precompile_script_success:
        print('Skipping post-compilation script')
        return
    print('Custom post-compilation script running now')

pre()

env.AddPostAction("$BUILD_DIR/${PROGNAME}.hex", post)