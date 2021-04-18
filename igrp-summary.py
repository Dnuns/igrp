'''
What the script does:
    + sign in to Nosi's website;
    + place the user and password;
    + go to SIGE (Sistema Integrado de Gestao Escolar | Integrated School Management System);
    + Go to the field write summary
'''
import config
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from time import sleep


browser = webdriver.Firefox()
browser.get('https://nosiapps.gov.cv/redglobal/redglobal.glb_dispatcher.login')

def login():

    for i in range (0,2):

        try:
            wait_login = WebDriverWait(browser, 20)
            utilizador = wait_login.until(EC.element_to_be_clickable((By.NAME, 'p_login')))
            browser.find_element_by_name('p_login').send_keys(config.username)

            Keys.TAB

            password = wait_login.until(EC.element_to_be_clickable((By.NAME, 'p_password')))
            browser.find_element_by_name('p_password').send_keys(config.password)

            button = wait_login.until(EC.element_to_be_clickable((By.NAME, 'p_button')))
            sleep(1)
            browser.find_element_by_name('p_button').click()

            sleep(3)

        except TimeoutException:
            print("Timed out waiting for login page to load")

def summary_page():

    try:
        #icone
        wait_menu = WebDriverWait(browser,20)
        icon = wait_menu.until(EC.element_to_be_clickable((By.CLASS_NAME,'app-icon')))
        browser.find_element_by_class_name('app-icon').click()

        #abrir o menu
        menu_lateral = wait_menu.until(EC.element_to_be_clickable((By.ID,'side-bar-ctrl')))
        browser.find_element_by_id('side-bar-ctrl').click()

        #Menu gestao de disciplina
        menu_gestao_disciplina = wait_menu.until(EC.element_to_be_clickable((By.LINK_TEXT,'Gestão de Disciplina')))
        browser.find_element_by_link_text('Gestão de Disciplina').click()

        # Menu principal do professor
        menu_p_professor = wait_menu.until(EC.element_to_be_clickable((By.LINK_TEXT,'Menu Principal Professor')))
        browser.find_element_by_link_text('Menu Principal Professor').click()

        # menu sala de aula
        sala_aula = wait_menu.until(EC.element_to_be_clickable((By.LINK_TEXT,'Sala Aula')))
        browser.find_element_by_link_text('Sala Aula').click()

        #submenu resumo do dia
        resumo_dia = wait_menu.until(EC.element_to_be_clickable((By.LINK_TEXT,'Resumo do dia')))
        browser.find_element_by_link_text('Resumo do dia').click()

    except TimeoutException:
        print("Timed out waiting for summary_page to load")


#Init the script
login()
summary_page()
