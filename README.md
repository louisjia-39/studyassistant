# IB Economics Study Assistant

This is a Streamlit-based educational application to help students study IB Economics. Users can upload their IB Economics textbook in PDF format, and the app uses the OpenAI API to generate simplified explanations, full theory summaries, real-world examples, and an intelligent Q&A system.

## Features

- **Simplified Explanations:** Summarizes complex economic concepts into simple language.
- **Full Theory:** Provides comprehensive theoretical summaries.
- **Real-World Examples:** Illustrates concepts with practical examples.
- **Smart Q&A:** Answers custom questions based on textbook content.

## Setup

1. Install dependencies from `requirements.txt`.
2. Set environment variables:
   - `OPENAI_API_KEY`: your OpenAI API key.
   - `DATABASE_URL`: PostgreSQL connection string with `pg_trgm` extension enabled (if using history features).
3. Run the Streamlit app using:
   streamlit run main.py

## Deployment

The app can be deployed to platforms such as Streamlit Community Cloud or Render. Ensure that environment variables are configured in the deployment environment.
