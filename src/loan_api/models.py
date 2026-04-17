from sqlalchemy import Column, Float, ForeignKey, Integer, String
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class Applicant(Base):
    __tablename__ = "applicants"

    applicant_id = Column(String(10), primary_key=True)
    gender = Column(String(10))
    married = Column(String(5))
    dependents = Column(String(5))
    education = Column(String(20))

    employment = relationship("Employment", back_populates="applicant", uselist=False)
    loans = relationship("Loan", back_populates="applicant")


class Employment(Base):
    __tablename__ = "employment"

    employment_id = Column(String(10), primary_key=True)
    applicant_id = Column(String(10), ForeignKey("applicants.applicant_id"), index=True)
    self_employed = Column(String(5))
    applicant_income = Column(Integer)
    coapplicant_income = Column(Integer)

    applicant = relationship("Applicant", back_populates="employment")


class Loan(Base):
    __tablename__ = "loans"

    loan_id = Column(String(20), primary_key=True)
    applicant_id = Column(String(10), ForeignKey("applicants.applicant_id"), index=True)
    loan_amount = Column(Float)
    loan_amount_term = Column(Integer)
    credit_history = Column(Integer)
    property_area = Column(String(20))

    applicant = relationship("Applicant", back_populates="loans")


TABLE_MODELS = {
    "applicants": Applicant,
    "employment": Employment,
    "loans": Loan,
}
