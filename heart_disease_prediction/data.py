from prefect import task
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder
from sklearn.model_selection import train_test_split

@task
def get_data(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, header=None)
    df.columns = [
        'age', 'sex', 'cp', 'trestbps', 'chol', 'fbs', 'restecg', 'thalach', 'exang', 'oldpeak', 'slope', 'ca', 'thal', 'hd'	
    ]
    df_with_no_missing = df.loc[(df['ca'] != '?')
                        &
                        (df['thal'] != '?')]
    print(f"Final Number of records after preprocessing is {len(df)}")
    return df_with_no_missing

# Splitting the Data
@task
def split_data_for_train(df: pd.DataFrame):
    # Independent and Dependent Variables
    X = df.drop('hd', axis=1).copy()
    y = df['hd'].copy()

    # Seperating the Cols based on their types
    numerical_cols = ['age', 'sex', 'trestbps', 'chol', 'fbs', 'thalach', 'exang', 'oldpeak']
    categorical_cols = ['restecg', 'slope', 'thal', 'ca', 'cp'] # We will pass this through OneHotEncoder

    # Making the preprocessor that will be applied on the data
    preprocessor = ColumnTransformer(
        transformers=[
            ('num', 'passthrough', numerical_cols),                  # Keep numerical columns as is
            ('cat', OneHotEncoder(drop='first'), categorical_cols)   # One-hot encode categorical columns
        ]
    )

    # We only need to detect the heart disease, not their severity
    y_not_zero = y > 0
    y[y_not_zero] = 1

    # SPLIT
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    # Fit and transform the data using the preprocessor
    # X_train_transformed = preprocessor.fit_transform(X_train)
    # X_test_transformed = preprocessor.transform(X_test)

    return X_train, X_test, y_train, y_test, preprocessor