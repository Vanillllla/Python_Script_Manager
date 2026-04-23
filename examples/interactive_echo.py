print("Interactive echo script started.")
print("Type something and press Enter. Type 'exit' to stop.")

while True:
    try:
        value = input("> ")
    except EOFError:
        break
    if value.strip().lower() == "exit":
        print("Stopping interactive echo script.")
        break
    print(f"Echo: {value}")

