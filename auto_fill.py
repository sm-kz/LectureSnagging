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


# 表url
url = 'https://docs.qq.com/form/page/DVURQaVNJZkJueVFC#/fill'

# 表内容
data = {
    '请填写姓名': 'xx',
    '请填写班级': 'xx',
    '请填写学号': 'xx'
}

#年 月 日 时 分 秒
run_time = [2025, 12, 19, 18, 13, 30]

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
tt = datetime.datetime(run_time[0],run_time[1],run_time[2],run_time[3],run_time[4],run_time[5])
while True:
    ct = datetime.datetime.now()
    if ct >= tt:
        break
    time.sleep(0.5)

# cookie处理
cookies_file = 'cookies.pkl'
need_login = True

if os.path.exists(cookies_file):
    driver.get(url)
    # time.sleep(0.5)
    
    with open(cookies_file, 'rb') as f:
        cookies = pickle.load(f)
    
    for cookie in cookies:
        try:
            driver.add_cookie(cookie)
        except:
            continue
    
    driver.refresh()
    # time.sleep(0.5)
    
    # 检查是否登录成功
    try:
        WebDriverWait(driver, 3).until(
            EC.presence_of_element_located((By.XPATH, "//button[text()='提交']"))
        )
        need_login = False
    except:
        need_login = True

if need_login:
    driver.get(url)
    input("\n请手动登录...\n登录成功点击Enter\n")
    
    cookies = driver.get_cookies()
    with open(cookies_file, 'wb') as f:
        pickle.dump(cookies, f)

# 选择
# k = WebDriverWait(driver, 20).until(
#         EC.element_to_be_clickable((By.XPATH, "//label[contains(., '男')]"))
#     )
# k.click()

# 填空
for key in data:
    xpath = f"//span[text()='{key}']/ancestor::div[@class='question-title']/following-sibling::div[@class='question-content']//textarea"
    
    k = WebDriverWait(driver, 2).until(
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
confirm_div.click()
