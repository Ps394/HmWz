import psutil


memory = psutil.virtual_memory()

discordbot = psutil.Process(22563)

print(f"Total memory: {memory.total / (1024 ** 3):.2f} GB")
print(f"Available memory: {memory.available / (1024 ** 3):.2f} GB")
print(f"Used memory: {memory.used / (1024 ** 3):.2f} GB")
print(f"Memory usage: {memory.percent}%")

cpu = psutil.cpu_percent(interval=1)
print(f"CPU usage: {cpu}%")

print(f"Discord bot memory usage: {discordbot.memory_info().rss / (1024 ** 2):.2f} MB")