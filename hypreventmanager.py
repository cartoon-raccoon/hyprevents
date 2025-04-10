from hyprevents import get_eventhandler


def main():
    eventhandler = get_eventhandler()
    eventhandler.load_all_dispatchers()
    eventhandler.mainloop()
    
if __name__ == "__main__":
    main()