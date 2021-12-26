'''
What the script does:
    + sign in to Nosi's website;
    + place the user and password;
    + go to SIGE (Sistema Integrado de Gestao Escolar | Integrated School Management System);
    + go to the field write summary
    + go to the field of absence
    + go to the fiel to download the list of students
'''
import config
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from time import sleep

class igrp_script:

    def __init__(self, web_driver_arg):
       driver = web_driver_arg 
       

    def login(self):

        try:
            driver.get('https://nosiapps.gov.cv/redglobal/redglobal.glb_dispatcher.login') #works but Nosi made a new page to loggin Autentika
            wait_login = WebDriverWait(driver, 30)
            utilizador = wait_login.until(EC.element_to_be_clickable((By.ID, 'usernameUserInput')))
            driver.find_element_by_id('usernameUserInput').send_keys(config.username)

            Keys.TAB

            password = wait_login.until(EC.element_to_be_clickable((By.ID, 'password')))
            driver.find_element_by_id('password').send_keys(config.password)

            button = wait_login.until(EC.element_to_be_clickable((By.XPATH, '//button[@class="btn p-1 btn-block rounded-0 mt-4 text-uppercase text-white fs-14 bg-dark"]')))
            driver.find_element_by_xpath('//button[@class="btn p-1 btn-block rounded-0 mt-4 text-uppercase text-white fs-14 bg-dark"]').click()

            #icone
            wait_menu = WebDriverWait(driver,30)
            icon = wait_menu.until(EC.element_to_be_clickable((By.CLASS_NAME,'app-icon')))
            driver.find_element_by_class_name('app-icon').click()

            #abrir o menu
            menu_lateral = wait_menu.until(EC.element_to_be_clickable((By.ID,'side-bar-ctrl')))
            driver.find_element_by_id('side-bar-ctrl').click()

            #Menu gestao de disciplina
            menu_gestao_disciplina = wait_menu.until(EC.element_to_be_clickable((By.LINK_TEXT,'Gestão de Disciplina')))
            driver.find_element_by_link_text('Gestão de Disciplina').click()

            #Menu principal do professor
            menu_p_professor = wait_menu.until(EC.element_to_be_clickable((By.LINK_TEXT,'Menu Principal Professor')))
            driver.find_element_by_link_text('Menu Principal Professor').click()

        except TimeoutException:
            print("Timed out waiting for login page to load")


    def summary_page(self):

        try:

            #menu sala de aula
            wait_menu = WebDriverWait(driver,30)
            sala_aula = wait_menu.until(EC.element_to_be_clickable((By.LINK_TEXT,'Sala Aula')))
            driver.find_element_by_link_text('Sala Aula').click()

            #submenu resumo do dia
            resumo_dia = wait_menu.until(EC.element_to_be_clickable((By.LINK_TEXT,'Resumo do dia')))
            driver.find_element_by_link_text('Resumo do dia').click()

        except TimeoutException:
            print("Timed out waiting for summary_page to load")


    def absence_page(self):

        try:

            #menu sala de aula
            wait_menu = WebDriverWait(driver,30)
            diretor_de_turma = wait_menu.until(EC.element_to_be_clickable((By.LINK_TEXT,'Diretor Turma')))
            driver.find_element_by_link_text('Diretor Turma').click()

            #submenu resumo do dia
            resumo_dia = wait_menu.until(EC.element_to_be_clickable((By.LINK_TEXT,'Alunos - Faltas e Notas')))
            driver.find_element_by_link_text('Alunos - Faltas e Notas').click()

        except TimeoutException:
            print("Timed out waiting for absence_page to load")


if __name__ == '__main__':
    
    driver = webdriver.Firefox()
    igrp_instance = igrp_script(driver)
    igrp_instance.login()

    while True:
        option = str(input('What do you want to do. \n1- whrite summary \n2- get absence \n3- quit\n'))

        if option == '1':
            igrp_instance.summary_page()
        elif option == '2':
            igrp_instance.absence_page()
        elif option == '3':
            driver.quit()
            break
        else:
            print('\n=================')
            print('Invalid option!!!')
            print('=================\n')