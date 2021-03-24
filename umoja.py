import pandas as pd
import numpy as np
import math
import argparse
import logging
import warnings
from pandas.core.common import SettingWithCopyWarning
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=SettingWithCopyWarning)

from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import StratifiedKFold, KFold, train_test_split
from sklearn.metrics import roc_auc_score
from xgboost import XGBClassifier

logging.getLogger().setLevel(logging.INFO)


if __name__ == '__main__':
  parser = argparse.ArgumentParser()
  parser.add_argument('--scale_pos_weight',
                      type = float,
                      default = 8.1922929,
                      help = 'Control the balance of positive and negative weights, useful for unbalanced classes.')
  parser.add_argument('--colsample_bylevel',
                      type = float,
                      default = 0.8,
                      help = 'the subsample ratio of columns for each level.')
  parser.add_argument('--eta',
                      type = float,
                      default = 0.143242,
                      help = 'Step size shrinkage used in update to prevent overfitting.')
  parser.add_argument('--max-depth',
                      type = int,
                      default = 10,
                      help = 'Maximum depth of a tree.')
  parser.add_argument('--n_estimators',
                      type = int,
                      default = 800 ,
                      help = 'Number of trees to fit.')
  parser.add_argument('--reg_alpha',
                      type = float,
                      default = 0.8,
                      help = 'L1 regularization term on weights.')
  args = parser.parse_args()

  def prep_data():
    # Load data
    all_data=pd.read_csv('https://raw.githubusercontent.com/Josepholaidepetro/Umojahack/main/maven/Train.csv')
    print("all_data size is : {}".format(all_data.shape))
    return all_data

  def preprocess():
    # call the function
    all_data = prep_data()
    # Convert date columns to datetime datatypes 
    for i in all_data.columns:
      if i[-4:] == 'Date':
        all_data[str(i)] = pd.to_datetime(all_data[str(i)],infer_datetime_format=True, errors='coerce')

    # noticed some strange occurence in the age column, as regarding the max and min
    # pre-processing the age column
    all_data['Age'].loc[all_data['Age'] < 0] = all_data['Age'].loc[all_data['Age'] < 0] * -1
    all_data['Age'] = np.where(all_data['Age'] == 320, 120, all_data['Age'])
    all_data['Age'] = np.where(all_data['Age'] > 320, 99, all_data['Age'])
    return all_data

  def extract_date_info():
    # call the function
    all_data = preprocess()

    # Extract Date features
    date_col = ['Policy Start Date', 'Policy End Date', 'First Transaction Date']

    all_data['Date diff'] = (all_data['Policy End Date'].dt.year - all_data['Policy Start Date'].dt.year) * 12 \
    + (all_data['Policy End Date'].dt.month - all_data['Policy Start Date'].dt.month)
    for feat in date_col:
        all_data[feat +'_day'] = all_data[feat].dt.day
        all_data[feat +'_month'] = all_data[feat].dt.month
        all_data[feat +'_quarter'] = all_data[feat].dt.quarter
    all_data.drop(columns=date_col,axis=1,inplace=True)
    return all_data

  def deal_missing_data():
    all_data = extract_date_info()
    # copy data
    all_data1 = all_data.copy()

    # categorical and continuous features
    cat_feat = all_data1.select_dtypes(exclude = np.number).columns
    num_feat = all_data1.select_dtypes(exclude = object).columns

    # Deal with missing values
    for col in num_feat:
      if col != 'target':
        all_data1[col].fillna(-999, inplace = True)  
        
    for col in cat_feat:
      all_data1[col].fillna('NONE', inplace = True)
      
    return all_data1

  def feat_eng():
    all_data1 = deal_missing_data()
    all_data1['LGA_Name'] = all_data1['LGA_Name'].map(all_data1['LGA_Name'].value_counts().to_dict())
    all_data1['State'] = all_data1['State'].map(all_data1['State'].value_counts().to_dict())
    all_data1['Subject_Car_Make'] = all_data1['Subject_Car_Make'].map(all_data1['Subject_Car_Make'].value_counts().to_dict())
    all_data1['Subject_Car_Colour'] = all_data1['Subject_Car_Colour'].map(all_data1['Subject_Car_Colour'].value_counts().to_dict()) 
    mapper = {"Male":"M","Female":'F','Entity':'O','Joint Gender':'O',None:'O','NO GENDER':'O','NOT STATED':'O','SEX':'O', np.nan: 'O' }
    all_data1.Gender = all_data1.Gender.map(mapper)
    return all_data1

  def encode_var():
    all_data1 = feat_eng()
    for i in ['ProductName', 'Car_Category']:
      encoder = LabelEncoder()
      all_data1[str(i)] = encoder.fit_transform(all_data1[str(i)])

    # feat engineering with the encoded variable
    all_data1['no_pol_prod_name'] = all_data1['No_Pol'] + all_data1['ProductName']

    # drop columns
    all_data1.drop(columns=['ID', 'Subject_Car_Colour'],inplace=True)
    # convert columns with categorical columns to numbers
    all_data1=pd.get_dummies(all_data1)
    return all_data1

  def modelling_data():
    all_data1 = encode_var()

    #Get the train dataset
    train_n = all_data1.copy()
    target = 'target'
    features = [c for c in train_n.columns if c not in ['target']]

    scores = 0
    k = 5
    kf = StratifiedKFold(k)

    for i, (tr_idx, vr_idx) in enumerate(kf.split(train_n, train_n[target])):
        xtrain, ytrain = train_n.loc[tr_idx, features], train_n.loc[tr_idx, target]
        xval, yval = train_n.loc[vr_idx, features], train_n.loc[vr_idx, target]
        
      # training and validation
        model=XGBClassifier(scale_pos_weight=args.scale_pos_weight, 
                            max_depth=args.max_depth,
                            eta=args.eta, 
                            n_estimators=args.n_estimators, 
                            silent=True,
                            metrics='auc',
                            colsample_bylevel=args.colsample_bylevel,
                            reg_alpha=args.reg_alpha)
        model.fit(xtrain, ytrain, eval_set=[(xval,yval)], early_stopping_rounds=100,verbose=100)
        pred = model.predict(xval)

        #predicting on test set
        score = roc_auc_score(yval, pred)
        #
        scores += score/k

    roc_auc_scores = scores
    return roc_auc_scores
    roc_auc_score = modelling_data()
    print('accuracy=%.3f' % roc_auc_score)
    logging.info("accuracy={:.4f}".format(roc_auc_score))


 