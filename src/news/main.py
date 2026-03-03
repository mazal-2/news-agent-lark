import toml

config = toml.load("config.toml")
rss_urls = config["rss"]["urls"]
print("读取到的 RSS 源：", rss_urls)  # 用于验证