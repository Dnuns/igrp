'''
[ICOMPLETE]

What the script does:

    I PART:
    + sign in to Nosi's website;
    + place the user and password;
    + go to SIGE (Sistema Integrado de Gestao Escolar | Integrated School Management System);

    II PART:
        * download the list of students by class;
        * show output on a spreadsheet (if possible organized and formatted);

    III PART:
        *upload with data inputs entered in the downloaded spreadsheet.
'''
import config
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup as bs
from time import sleep


driver = webdriver.Firefox()
driver.get('https://nosiapps.gov.cv/redglobal/redglobal.glb_dispatcher.login')


def login():

    for i in range (0,2):

        try:
            wait = WebDriverWait(driver, 20)
            utilizador = wait.until(EC.element_to_be_clickable((By.NAME, 'p_login')))
            driver.find_element_by_name('p_login').send_keys(config.username)

            Keys.TAB

            password = wait.until(EC.element_to_be_clickable((By.NAME, 'p_password')))
            driver.find_element_by_name('p_password').send_keys(config.password)

            button = wait.until(EC.element_to_be_clickable((By.NAME, 'p_button')))
            sleep(1)
            driver.find_element_by_name('p_button').click()

            sleep(3)

        except TimeoutException:
            print("Timed out waiting for login page to load")


def abrir_menu():

    try:

        #icone
        wait = WebDriverWait(driver,20)
        icon = wait.until(EC.element_to_be_clickable((By.CLASS_NAME,'app-icon')))
        driver.find_element_by_class_name('app-icon').click()

        #abrir o menu
        menu_lateral = wait.until(EC.element_to_be_clickable((By.ID,'side-bar-ctrl')))
        driver.find_element_by_id('side-bar-ctrl').click()

        #Menu gestao de disciplina
        menu_gestao_disciplina = wait.until(EC.element_to_be_clickable((By.LINK_TEXT,'Gestão de Disciplina')))
        driver.find_element_by_link_text('Gestão de Disciplina').click()

        #Menu principal do professor
        menu_p_professor = wait.until(EC.element_to_be_clickable((By.LINK_TEXT,'Menu Principal Professor')))
        driver.find_element_by_link_text('Menu Principal Professor').click()

    except TimeoutException:
        print("Timed out waiting for summary_page to load")

def get_student_list():

    try:
        wait = WebDriverWait(driver,20)
        gestao_disciplina = wait.until(EC.element_to_be_clickable((By.XPATH, '/html/body/form/div[1]/div/div[2]/div/div[2]/div/div/div/ul/li[3]/a/span')))
        driver.find_element_by_xpath('/html/body/form/div[1]/div/div[2]/div/div[2]/div/div/div/ul/li[3]/a/span').click()# menu gestao_disciplina horizontal

        atribuir_notas = wait.until(EC.element_to_be_clickable((By.XPATH, '/html/body/form/div[1]/div/div[2]/div/div[2]/div/div/div/div/div[3]/div/div/div/div/div/a[3]/span')))
        driver.find_element_by_xpath('/html/body/form/div[1]/div/div[2]/div/div[2]/div/div/div/div/div[3]/div/div/div/div/div/a[3]/span').click()# atribuir notas

    except TimeoutException:
            print("Timed out waiting for list to be downloaded")


# II PART

#filtro_nota = esperar.until(EC.element_to_be_clickable((By.XPATH, '/html/body/form/div[1]/div/div[2]/div/div[4]/div[2]/div/div/div[2]/div/div[3]/span/span[1]/span')))
# driver.find_element_by_xpath('/html/body/form/div[1]/div/div[2]/div/div[4]/div[2]/div/div/div[2]/div/div[3]/span/span[1]/span').click()# atribuir notas filtro ano


#Init the script
login()
abrir_menu()
get_student_list()

sleep(10)
