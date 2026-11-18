import importlib,sys,traceback
def main():
    mod=importlib.import_module("tests.test_app")
    names=sorted(n for n in dir(mod) if n.startswith("test_")); failed=0
    for name in names:
        try: getattr(mod,name)(); print(f"PASS  {name}")
        except Exception: failed+=1; print(f"FAIL  {name}"); traceback.print_exc()
    print(f"\n{len(names)-failed} passed, {failed} failed")
    return 1 if failed else 0
if __name__=="__main__": sys.exit(main())
