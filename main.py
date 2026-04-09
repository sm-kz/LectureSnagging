import flet as ft
from flet_core import colors
import threading
import datetime
import time
import os
import sys
import json
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys

if getattr(sys, 'frozen', False):
    # 打包后的路径
    base_path = os.path.dirname(sys.executable)
else:
    # 源码运行的路径
    base_path = os.path.dirname(os.path.abspath(__file__))

config_path = os.path.join(base_path, 'config.json')
profile_path = os.path.join(base_path, 'EdgeProfile')

# 全局信号
stop_event = threading.Event()
is_editing_mode = False

def main(page: ft.Page):
    page.title = "抢表助手"
    page.window.width = 480
    page.window.height = 720
    page.window.center() 
    page.update()

    # --- 动态管理填写项 ---
    COMMON_STYLE = {
        "border_color": colors.with_opacity(0.35, colors.WHITE70), 
        "bgcolor": colors.with_opacity(0.15, colors.GREY_900),
        "border_radius": 10, # 加一点圆角，看起来更高级
        "filled": True,
        "focused_border_color": colors.BLUE_400, # 选中时的颜色
    }
    # 初始默认字段
    fields_list = [
        ft.TextField(label="姓名", value="", expand=True, **COMMON_STYLE),
        ft.TextField(label="班级", value="", expand=True, **COMMON_STYLE),
        ft.TextField(label="学号", value="", expand=True, **COMMON_STYLE),
    ]
    
    # 放置每行两个 TextField 的容器
    dynamic_grid = ft.Column(spacing=10)

    def rebuild_grid():
        dynamic_grid.controls.clear()
        for i in range(0, len(fields_list), 2):
            row_content = fields_list[i : i + 2]
            row_controls = []
            for f in row_content:
                # 统一设置一个舒服的内边距
                f.content_padding = ft.padding.symmetric(vertical=15, horizontal=10)
                
                if is_editing_mode:
                    row_controls.append(ft.Stack([
                        f,
                        ft.Container(
                            content=ft.TextButton(
                                content=ft.Text("×", size=18, weight="bold", color=colors.RED_400),
                                on_click=lambda e, obj=f: delete_field(obj),
                            ),
                            right=0, top=-5,
                        )
                    ], expand=True))
                else:
                    row_controls.append(f)
            
            if len(row_controls) == 1:
                row_controls.append(ft.Container(expand=True))
            dynamic_grid.controls.append(ft.Row(controls=row_controls, spacing=10))
        page.update()

    def delete_field(field_obj):
        """删除指定的填写项，并全网搜捕它的真实名字"""
        target_name = ""
        
        # 1. 优先去 data 字典里找我们备份的原始名字
        if isinstance(field_obj.data, dict):
            target_name = field_obj.data.get("original_label", "") or field_obj.data.get("l", "")
            
        # 2. 如果 data 里没有，去别的属性里抠出来
        if not target_name:
            if field_obj.label:
                target_name = field_obj.label
            elif field_obj.prefix_text:
                # 假设你用了 prefix_text 方案，把前缀修饰词切掉
                target_name = field_obj.prefix_text.replace("新标题:", "").strip()
            elif field_obj.hint_text:
                target_name = field_obj.hint_text.replace("原标题：", "").strip()

        # 3. 清洗可能残留的 \n 或括号等修饰符
        target_name = target_name.replace("\n", "").replace("修改标题 (原:", "").replace(")", "").strip()
        
        # 4. 终极兜底
        if not target_name:
            target_name = "未命名项目"

        # 执行删除
        fields_list.remove(field_obj)
        write_log(f"🗑️ 已删除项: {target_name}", colors.RED_400)
        rebuild_grid()

    def add_field_click(e):
        """点击图标增加新选项框"""
        label_text = f"自定义项 {len(fields_list)+1}"
        # 1. 基础创建
        new_field = ft.TextField(label=label_text, expand=True)
        
        # 2. 核心初始化：无论在什么模式，data 必须有值
        new_field.data = {"v": "", "l": label_text}
        
        # 3. 如果当前在管理模式，强制变色并设置前缀
        if is_editing_mode:
            new_field.label = "" 
            new_field.prefix_text = "新标题: "
            new_field.prefix_style = ft.TextStyle(color=colors.AMBER_400, weight="bold")
            new_field.value = label_text # 让用户直接在框里改名
            new_field.border_color = colors.AMBER_400
            new_field.content_padding = ft.padding.symmetric(vertical=15, horizontal=10)
        
        fields_list.append(new_field)
        rebuild_grid() # 刷新界面
        write_log(f"➕ 已增加项: {label_text}")

    # --- 固定输入项 ---
    url_input = ft.TextField(
        label="表单 URL", 
        value="https://docs.qq.com/form/page/DVWpVTkRqVHZQa3Fm#/fill", 
        multiline=True, max_lines=3, expand=False, 
        width=page.window.width, **COMMON_STYLE)
    time_input = ft.TextField(label="运行时间", 
                              value="2026-04-09 11:00:00", 
                              expand=True, **COMMON_STYLE)
    delay_input = ft.TextField(label="确认延时 (秒)", value="2", expand=True, **COMMON_STYLE)
    time_delay_row = ft.Row(
        controls=[time_input, delay_input],
        spacing=10
    )

    # --- 日志区 ---
    log_content = ft.Column(spacing=2, scroll=ft.ScrollMode.ALWAYS, expand=True)
    log_container = ft.Container(
        content=log_content,
        border=ft.border.all(1, colors.GREY_700),
        border_radius=10,
        padding=10,
        bgcolor=colors.BLACK,
        width=page.window.width,
        expand=True
    )

    def write_log(msg, clr=colors.WHITE):
        log_content.controls.append(ft.Text(f"[{time.strftime('%H:%M:%S')}] {msg}", color=clr, size=12))
        page.update()

    # --- Selenium 核心逻辑 (修改了 data_map 搜集方式) ---
    def automation_task(url, data_map, target_time_str, submit_delay):
        driver = None
        try:
            target_time = datetime.datetime.strptime(target_time_str, "%Y-%m-%d %H:%M:%S").timestamp()
            write_log("🚀 启动浏览器...")
            option = webdriver.EdgeOptions()
            option.add_argument(f"user-data-dir={profile_path}")
            driver = webdriver.Edge(options=option)
            
            if stop_event.is_set(): return
            driver.get('https://docs.qq.com')
            
            while driver.find_elements(By.XPATH, "//div[contains(@class, 'dui-button-container') and text()='登录']"):
                if stop_event.is_set(): return
                write_log("⚠️ 请在浏览器中扫码登录...", colors.ORANGE_800)
                time.sleep(2)
            
            write_log("✅ 登录成功，前往表单...")
            driver.get(url)

            while time.time() < target_time:
                if stop_event.is_set(): return
                time.sleep(0.01)

            write_log("🔥 时间到！开始填写...", colors.BLUE_400)
            driver.refresh()
            
            try:
                WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.XPATH, "//li[contains(@class,'dui-tabs-bar-item') and text()='填写']"))).click()
            except: pass

            # 动态填写逻辑：循环所有 fields_list 中的 label 和 value
            for key, val in data_map.items():
                if stop_event.is_set(): return
                xpath = f"//span[contains(text(),'{key}')]/ancestor::div[@class='question-title']/following-sibling::div[@class='question-content']//textarea"
                try:
                    element = WebDriverWait(driver, 3).until(EC.presence_of_element_located((By.XPATH, xpath)))
                    element.send_keys(Keys.CONTROL, 'a')
                    element.send_keys(Keys.BACKSPACE)
                    element.clear()
                    element.send_keys(val)
                except: 
                    write_log(f"⚠️ 找不到字段: {key}", colors.RED_200)

            if stop_event.is_set(): return
            submit_btn = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.XPATH, "//button[text()='提交']")))
            
            if submit_delay > 0:
                while time.time() - target_time < submit_delay:
                    if stop_event.is_set(): return
                    time.sleep(0.01)

            driver.execute_script("arguments[0].click();", submit_btn)
            
            try:
                WebDriverWait(driver, 3).until(EC.element_to_be_clickable((By.XPATH, "//div[@class='dui-button-container' and text()='确认']"))).click()
                write_log("🎉 任务圆满完成！", colors.GREEN_400)
            except: return

        except Exception as e:
            write_log(f"❌ 错误: {str(e)}", colors.RED_400)
        finally:
            if driver: driver.quit()
            start_btn.disabled = False
            cancel_btn.visible = False
            page.update()

    # --- 按钮与操作 ---
    def start_click(e):
        stop_event.clear()
        start_btn.disabled = True
        cancel_btn.visible = True
        log_content.controls.clear()
        # 动态搜集当前所有输入框的数据
        current_data = {f.label: f.value for f in fields_list}
        
        t = threading.Thread(
            target=automation_task, 
            args=(url_input.value, current_data, time_input.value, float(delay_input.value)),
            daemon=True
        )
        t.start()
        write_log("▶️ 抢表任务已启动")
        page.update()

    def cancel_click(e):
        stop_event.set()
        cancel_btn.visible = False
        write_log("⏹️ 正在紧急取消任务...", colors.RED_300)
        page.update()

    start_btn = ft.ElevatedButton(
        content=ft.Text("🚀 启动抢表", weight="bold"), 
        on_click=start_click, width=320, height=45,
        style=ft.ButtonStyle(bgcolor=colors.BLUE_800, color=colors.WHITE)
    )

    cancel_btn = ft.OutlinedButton(
        content=ft.Text("🛑 取消抢表"),
        on_click=cancel_click, width=320, height=45,
        style=ft.ButtonStyle(color=colors.RED_400),
        visible=False
    )

    # --- 底部工具栏 (增减选项) ---
    def toggle_edit_titles(e):
        global is_editing_mode
        is_editing_mode = not is_editing_mode
        
        for f in fields_list:
            # 强制初始化 data 结构，防止手动添加导致的 KeyError
            if not isinstance(f.data, dict):
                f.data = {"v": f.value, "l": f.label if f.label else "自定义项"}

            if is_editing_mode:
                # 进入管理模式：备份当前值，把标签显示到输入框里
                f.data["v"] = f.value 
                f.data["l"] = f.label if f.label else f.data["l"]
                
                f.label = "" 
                f.prefix_text = "新标题: "
                f.prefix_style = ft.TextStyle(color=colors.AMBER_400, weight="bold")
                f.value = f.data["l"] 
                f.border_color = colors.AMBER_400
                f.content_padding = ft.padding.symmetric(vertical=15, horizontal=10)
            else:
                # 退出管理模式：把输入框里的新标题存回 label
                new_title = f.value if f.value else f.data["l"]
                f.label = new_title
                f.value = f.data.get("v", "")
                f.prefix_text = None
                f.border_color = COMMON_STYLE["border_color"]
                f.bgcolor = COMMON_STYLE["bgcolor"]
                f.filled = COMMON_STYLE["filled"]
                f.border_radius = COMMON_STYLE["border_radius"]

        edit_btn.style = ft.ButtonStyle(color=colors.AMBER_400 if is_editing_mode else colors.GREY_400)
        rebuild_grid()

    # --- 核心函数：改名对话框 ---
    rename_target = None
    rename_input = ft.TextField(label="输入新标题")

    def confirm_rename(e):
        if rename_target and rename_input.value:
            rename_target.label = rename_input.value
            write_log(f"📝 标题已修改为: {rename_input.value}")
            rename_dialog.open = False
            page.update()

    rename_dialog = ft.AlertDialog(
        title=ft.Text("修改标题"),
        content=rename_input,
        actions=[
            ft.TextButton("取消", on_click=lambda _: setattr(rename_dialog, 'open', False) or page.update()),
            ft.TextButton("确定", on_click=confirm_rename),
        ],
    )
    page.dialog = rename_dialog

    # --- 修改 add_field_click 确保新项也支持编辑 ---
    def add_field_click(e):
        label_text = "自定义项"
        
        new_field = ft.TextField(label=label_text, expand=True, **COMMON_STYLE)
        # 初始化必须包含 v(value) 和 l(label)
        new_field.data = {"v": "", "l": label_text}
        
        if is_editing_mode:
            new_field.label = "" 
            new_field.prefix_text = "新标题: "
            new_field.prefix_style = ft.TextStyle(color=colors.AMBER_400, weight="bold")
            new_field.value = label_text
            new_field.border_color = colors.AMBER_400
            new_field.content_padding = ft.padding.symmetric(vertical=15, horizontal=10)
        
        fields_list.append(new_field)
        # 强制重新构建，清除所有旧引用
        rebuild_grid()
        write_log(f"➕ 已增加项: {label_text}")

    def save_config(e=None):
        """将当前所有配置保存到本地 json 文件"""
        # 如果正在编辑模式，先切回普通模式以确保获取正确的 Label 和 Value
        global is_editing_mode
        if is_editing_mode:
            toggle_edit_titles(None)

        config_data = {
            "url": url_input.value,
            "run_time": time_input.value,
            "delay": delay_input.value,
            "fields": []
        }
        
        # 搜集所有动态字段
        for f in fields_list:
            config_data["fields"].append({
                "label": f.label,
                "value": f.value
            })
        
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config_data, f, ensure_ascii=False, indent=4)
            write_log("💾 配置已成功保存到本地文件", colors.GREEN_400)
        except Exception as ex:
            write_log(f"❌ 保存失败: {str(ex)}", colors.RED_400)

    def load_config():
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                
                # 恢复固定项
                url_input.value = config.get("url", url_input.value)
                time_input.value = config.get("run_time", time_input.value)
                delay_input.value = config.get("delay", delay_input.value)
                
                # 恢复动态项
                loaded_fields = config.get("fields", [])
                if loaded_fields:
                    fields_list.clear() # 清除默认的姓名班级，改用读取的
                    for item in loaded_fields:
                        fields_list.append(
                            ft.TextField(
                                label=item["label"], 
                                value=item["value"], 
                                expand=True,
                                **COMMON_STYLE
                            )
                        )
                write_log("📂 已从本地加载配置", colors.GREEN_400)
            except Exception as ex:
                write_log(f"⚠️ 加载配置失败: {str(ex)}", colors.ORANGE_400)

    # --- 按钮定义 ---
    edit_btn = ft.TextButton(
        "⚙️", 
        tooltip="切换标题编辑模式", 
        on_click=toggle_edit_titles
    )

    # --- UI 布局 ---
    tools_row = ft.Row(
        [
            ft.Text("添加", size=12, color=colors.GREY_400),
            ft.TextButton("➕", on_click=add_field_click),
            ft.Text("管理", size=12, color=colors.GREY_400),
            edit_btn, # 使用上面定义的变量
            ft.Text("保存", size=12, color=colors.GREY_400),
            ft.TextButton("💾", on_click=save_config)
        ],
        alignment=ft.MainAxisAlignment.CENTER
    )

    # 初始化界面
    load_config()
    rebuild_grid()

    # --- 页面排版 ---
    main_layout = ft.Column(
        [
            ft.Row([ft.Text("抢表助手配置", size=24, weight="bold", color=colors.BLUE_100)], alignment="center"),
            url_input,
            time_delay_row,
            ft.Divider(height=10, color=colors.GREY_800),
            dynamic_grid,
            tools_row,
            ft.Row([ft.Column([start_btn, cancel_btn], horizontal_alignment="center", spacing=10)], alignment="center"),
            ft.Text("运行状态:", size=14, weight="bold"),
            log_container, # 👈 此时它在 main_layout 中会吞掉所有剩下的高度
        ],
        expand=True,
        tight=True,
    )
    page.add(main_layout)

if __name__ == "__main__":
    ft.app(target=main)
