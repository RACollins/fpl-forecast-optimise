import streamlit as st
import numpy as np
import pandas as pd
import requests
import json
import plotly.express as px

###################
### Page Config ###
###################

st.set_page_config(
    page_title="FPL stats App",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="auto",
)

st.markdown(
    """
    <style>
    .stSlider [data-baseweb=slider]{
        justify-content: center;
        width: 66%;
        left: 11%;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

#################
### Constants ###
#################

col_name_change_dict = {
    "event": "GW",
    "event_total": "GW Total",
    "player_name": "Manager",
    "entry": "ID",
    "entry_name": "Team Name",
    "rank": "Rank",
    "last_rank": "Last Rank",
    "rank_sort": "Rank Sort",
    "overall_rank": "Overall Rank",
    "total": "Total Points",
    "total_points": "Total Points",
    "points": "Points",
    "value": "Value",
    "bank": "Bank",
    "event_transfers": "Transfers",
    "event_transfers_cost": "Transfer Costs",
    "points_on_bench": "Points on Bench",
}

#################
### Functions ###
#################


@st.cache_data
def get_league_data(leagueID):
    if not isinstance(leagueID, int):
        leagueID = int(leagueID)
    fpl_league_url = (
        f"https://fantasy.premierleague.com/api/leagues-classic/{leagueID}/standings/"
    )
    respose = requests.get(fpl_league_url)
    fpl_league_respose_json = respose.json()
    league_df = pd.DataFrame(fpl_league_respose_json["standings"]["results"]).rename(
        columns=col_name_change_dict
    )
    return league_df


@st.cache_data
def get_all_mngrs_all_gws_df(league_df):
    all_gws_url_template = (
        "https://fantasy.premierleague.com/api/entry/{manager_id}/history/"
    )
    all_gws_df_list = []
    for i, manager_id in enumerate(league_df["ID"]):
        respose = requests.get(all_gws_url_template.format(manager_id=manager_id))
        all_gws_respose_json = respose.json()
        all_gws_df = pd.DataFrame(all_gws_respose_json["current"])
        all_gws_df["ID"] = manager_id
        all_gws_df["Team Name"] = league_df.loc[i, "Team Name"]
        all_gws_df["Manager"] = league_df.loc[i, "Manager"]
        all_gws_df_list.append(all_gws_df)
    all_mngrs_all_gws_df = (
        pd.concat(all_gws_df_list)
        .rename(columns=col_name_change_dict)
        .drop(["Rank", "Rank Sort"], axis=1)
    )
    ### Divide by 10
    all_mngrs_all_gws_df["Bank"] = all_mngrs_all_gws_df["Bank"] * 1e5
    all_mngrs_all_gws_df["Value"] = all_mngrs_all_gws_df["Value"] * 1e5
    ### Add league rank as "Rank"
    all_mngrs_all_gws_df["Rank"] = np.nan
    max_gw = all_mngrs_all_gws_df["GW"].max()
    all_mngrs_all_gws_df["Rank"] = all_mngrs_all_gws_df.groupby("GW")[
        "Total Points"
    ].rank(method="min", ascending=False)
    ### Add "Total" columns
    for col in ["Transfers", "Transfer Costs", "Points on Bench"]:
        all_mngrs_all_gws_df[f"Total {col}"] = all_mngrs_all_gws_df.groupby("Manager")[
            col
        ].cumsum()
    ### Add "Form" column
    all_mngrs_all_gws_df["Form"] = (
        all_mngrs_all_gws_df.groupby("Manager")["Points"]
        .rolling(window=4, min_periods=1)
        .mean()
        .droplevel(0)
        .div(11)
    )
    return all_mngrs_all_gws_df


st.title("FPL League Dashboard")
st.subheader("Input your league ID to view various statistics")

leagueID = st.number_input(
    "League ID", value=None, placeholder="Type your league ID here...", step=1
)

render_elements = False
if leagueID != None:
    render_elements = True
else:
    league_df = None
    st.info(
        "How to find you league ID:  \n"
        "👉 Login to your FPL account  \n"
        "👉 Select the 'Leagues & Cups' tab  \n"
        "👉 Select a league  \n"
        "👉 Copy ID from the URL  \n"
    )

if render_elements:
    with st.sidebar:
        st.header("Info...")
    tab1, tab2, tab3 = st.tabs(["Summary", "Graphs", "Analysis"])
    with tab1:
        league_df = get_league_data(leagueID)
        all_mngrs_all_gws_df = get_all_mngrs_all_gws_df(league_df)
        max_gw = all_mngrs_all_gws_df["GW"].max()
        st.dataframe(
            league_df[
                ["Rank", "Manager", "Team Name", "GW Total", "Total Points"]
            ].style.format(thousands=","),
            use_container_width=True,
            hide_index=True,
        )
    with tab2:
        # st.dataframe(all_mngrs_all_gws_df, use_container_width=True)
        with st.container(border=True):
            y_axis_option = st.selectbox(
                "Pick a Parameter to Plot",
                [
                    "Points",
                    "Total Points",
                    "Rank",
                    "Overall Rank",
                    "Bank",
                    "Value",
                    "Form",
                    "Transfers",
                    "Transfer Costs",
                    "Points on Bench",
                    "Total Transfers",
                    "Total Transfer Costs",
                    "Total Points on Bench",
                ],
            )
            # print(all_mngrs_all_gws_df.columns.to_list())
            gw_range = st.slider("Select GW range", 1, max_gw, (1, max_gw))
            fig = px.line(
                all_mngrs_all_gws_df[
                    all_mngrs_all_gws_df["GW"].between(gw_range[0], gw_range[1])
                ],
                x="GW",
                y=y_axis_option,
                color="Manager",
                markers=True,
            )
            st.plotly_chart(fig, theme="streamlit", use_container_width=True)
