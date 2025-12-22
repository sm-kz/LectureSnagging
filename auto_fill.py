from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.service import Service
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import datetime
import time
import pickle
import os

"""=====================按情况更改========================"""
# 表url
url = 'https://docs.qq.com/form/page/DVUJ6ekZUdXNpQ1NY#/fill'

# 表内容, 可以模糊匹配
data = {
    '姓名': 'xx',
    '班级': 'xx',
    '学号': 'xx'
}

#年 月 日 时 分 秒
run_time = [2025, 12, 22, 15, 33, 30]

# 可选, 运行时间过多少秒提交
submit_time = 4.0
"""==================================================="""

# 创建 Edge 浏览器对象
option = webdriver.EdgeOptions()

option.add_experimental_option('excludeSwitches', ['enable-automation'])
option.add_experimental_option('useAutomationExtension', False)

# service = Service(driver_path)
driver = webdriver.Edge(options=option)

driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
    'source': 'Object.defineProperty(navigator, "webdriver", {get: () => undefined})'
})

#定时打开网页
tt = datetime.datetime(*run_time).timestamp()

# cookie处理
cookies_file = 'cookies.pkl'

# 检测腾讯文档首页cookie文件是否存在
base_url = 'https://docs.qq.com'  # 腾讯文档首页
driver.get(base_url)

if not os.path.exists(cookies_file):
    try:
        # 检查首页是否有登录按钮
        WebDriverWait(driver, 0.5).until(
            EC.presence_of_element_located((By.XPATH, 
                "//div[@class='dui-button-container' and text()='登录']"
            ))
        )

        print("需要登录...")
        input("请手动登录后按Enter...\n")

        # 保存cookies
        cookies = driver.get_cookies()
        with open(cookies_file, 'wb') as f:
            pickle.dump(cookies, f)

    except:
        pass
    
with open(cookies_file, 'rb') as f:
    cookies = pickle.load(f)

# 向网页添加cookie
for cookie in cookies:
        try:
            driver.add_cookie(cookie)
        except:
            continue
driver.refresh()

# 进入填表页面
driver.get(url)

# 轮询等待定时
while True:
    ct = time.time()
    if ct >= tt:
        break
    time.sleep(0.25)

# 切换到填写页面（如果是自己创建的则默认为统计页面）
try:
    fill = driver.find_element(
        By.XPATH, 
        "//li[contains(@class, 'dui-tabs-bar-item') and text()='填写']"
    )
    fill.click()
except:
    pass

# 选择
# k = WebDriverWait(driver, 20).until(
#         EC.element_to_be_clickable((By.XPATH, "//label[contains(., '男')]"))
#     )
# k.click()

# 填空
for key in data:
    xpath = f"//span[contains(text(), '{key}')]/ancestor::div[@class='question-title']/following-sibling::div[@class='question-content']//textarea"
    
    k = WebDriverWait(driver, 1).until(
        EC.element_to_be_clickable((By.XPATH, xpath))
            )
    k.send_keys(data[key])

# 提交按钮
k = WebDriverWait(driver, 1).until(
        EC.element_to_be_clickable((By.XPATH, "//button[text()='提交']"))
            )
driver.execute_script("arguments[0].click();", k)

time.sleep(0.1)
# 确认提交
confirm_div = driver.find_element(
    By.XPATH, 
    "//div[@class='dui-button-container' and text()='确认']"
)
while time.time() - tt < submit_time:
    time.sleep(0.2)

confirm_div.click()
    
