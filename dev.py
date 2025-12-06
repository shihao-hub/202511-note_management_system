import sys, os
os.chdir(os.path.dirname(__file__))
sys.path.append(os.path.abspath('app'))
sys.path.append(os.path.abspath('app.egg'))
os.chdir(os.path.join(os.path.dirname(__file__), "app"))
import main
main.main()
