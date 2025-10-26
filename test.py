import gspread
gc = gspread.service_account(filename="service_account.json")
sh = gc.open_by_key("1Ahv3CNsRvT0N5s-te8o3xkfwATbFuhAENpX0xoqM3Sw")
print(sh.title)
