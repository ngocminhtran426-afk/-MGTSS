import sys
import traceback

try:
    import easyocr
    print("Importing easyocr SUCCESS")
    reader = easyocr.Reader(['vi','en'])
    print("Loading Reader SUCCESS")
    print("DONE")
except Exception as e:
    traceback.print_exc(file=sys.stdout)
