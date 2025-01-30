# train_intent_classifier.py
import json
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report
from intents_data import intents

# Vorbereitung der Daten
texts = []
labels = []
for intent, examples in intents.items():
    for example in examples:
        texts.append(example)
        labels.append(intent)

# Aufteilen der Daten in Trainings- und Testsets mit stratifizierter Aufteilung
X_train, X_test, y_train, y_test = train_test_split(
    texts, labels, test_size=0.2, random_state=42, stratify=labels
)

# Erstellen einer Pipeline mit Vektorisierung und Klassifikation
pipeline = Pipeline([
    ('tfidf', TfidfVectorizer()),
    ('clf', LogisticRegression(max_iter=1000))
])

# Trainieren des Modells
pipeline.fit(X_train, y_train)

# Evaluierung des Modells
y_pred = pipeline.predict(X_test)
print(classification_report(y_test, y_pred))

# Speichern des trainierten Modells
import joblib
joblib.dump(pipeline, 'intent_classifier.pkl')
