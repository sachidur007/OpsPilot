from simulator.main import reset_fleet

def build_data():
    fleet = reset_fleet()
    summary = fleet["summary"]
    print(
        f"Opening scene ready. {summary['active']} active incidents, "
        f"{summary['healthy']} healthy services."
    )

if __name__ == "__main__":
    build_data()
