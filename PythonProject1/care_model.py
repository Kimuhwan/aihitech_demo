import speech_recognition as sr
import pyaudio

def STT():
    r = sr.Recognizer()
    with sr.Microphone() as source:
        audio = r.listen(source)
    try:
        result = r.recognize_google(audio, language='ko')
        print(result)
        return result

    except sr.UnknownValueError:
        print("Google Speech Recognition could not understand audio")
    except sr.RequestError as e:
        print("Could not request results from Google Speech Recognition service; {0}".format(e))

#check emergency 용 증상 및 부위 딕셔너리
intensity_dict = {
    "조금": 1, "약간": 1, "살짝": 1,
    "꽤": 2, "많이": 2, "상당히": 2,
    "너무": 3, "정말": 3, "심하게": 3, "매우": 3,
    "살려주세요" : 4
}
body_dict = {
    "머리가": 1.2,    # 뇌졸중 위험
    "가슴이": 1.5,    # 심장 위험
    "배가": 1.0,
    "다리기": 0.8
}


def check_emergency(String):
    divided_string = String.split(" ")
    body_part = ""
    intensity_word = ""
    intensity_score = 0
    body_score = 0
    total_score = 0

                        #"조금", "약간" → 1점
                        #"꽤", "많이" → 2점
                        #"너무", "정말", "심하게" → 3점
    for word in divided_string:
        if(word in body_dict.keys()):
            body_part = word
            body_score = body_dict[word]
        if(word in intensity_dict.keys()):
            intensity_score = intensity_dict[word]
            intensity_word += word

    total_score  = (body_score+1) * (intensity_score+1)
    return body_part, intensity_word, total_score



class elderly_profile:
    level = 0 #0: 정상, 1: 경미, 2: 중증, 3: 심각

    def __init__(self, name, age, disease, drug):
        self.name = name
        self.age = age
        self.disease = disease
        self.drug = drug

    def change_level(self, level): # 함수에 따라서 위험도를 변경하는 함수
        self.level = level

    def print_level(self): # 레벨 변수를 출력하는 함수
        return self.level

print(check_emergency(STT()))