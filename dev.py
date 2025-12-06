import sys, os
os.chdir(os.path.dirname(__file__))
sys.path.append(os.path.abspath('unit'))
sys.path.append(os.path.abspath('unit.egg'))
os.chdir(os.path.join(os.path.dirname(__file__), "unit"))
import main
main.main()
