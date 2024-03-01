from altair import Self
import streamlit as st
import datetime as datetime
from dataclasses import dataclass
import requests
import numpy as np
import pandas as pd
import plotly.express as px
import utils
from ast import literal_eval


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
    "element_in": "Player_in",
    "element_out": "Player_out",
    "element_in_cost": "Player_in_cost",
    "element_out_cost": "Player_out_cost",
}
hex_plotly_colour_list = [
    "#636EFA",
    "#EF553B",
    "#00CC96",
    "#AB63FA",
    "#FFA15A",
    "#19D3F3",
    "#FF6692",
    "#B6E880",
    "#FF97FF",
    "#FECB52",
]
rgba_plotly_colour_list = [
    "rgba(99, 110, 250, 1)",
    "rgba(239, 85, 59, 1)",
    "rgba(0, 204, 150, 1)",
    "rgba(171, 99, 250, 1)",
    "rgba(255, 161, 90, 1)",
    "rgba(25, 211, 243, 1)",
    "rgba(255, 102, 146, 1)",
    "rgba(182, 232, 128, 1)",
    "rgba(255, 151, 255, 1)",
    "rgba(254, 203, 82, 1)",
]
low_alpha_plotly_colour_list = [
    c.replace("1)", "0.33)") for c in rgba_plotly_colour_list
]
combined_plotly_colour_list = [
    j for i in zip(rgba_plotly_colour_list, low_alpha_plotly_colour_list) for j in i
]
rgba_tuples_list = [
    literal_eval(c.replace("rgba", "")) for c in combined_plotly_colour_list
]

###############
### Classes ###
###############


@dataclass
class LeagueData:
    leagueID: int
    standings_url_template: str
    history_url_template: str
    picks_url_template: str
    transfers_url_template: str
    bootstrap_static_url: str
    live_url_template: str

    def __post_init__(self):
        ### League info
        self.league_name, self.standings_df = self._get_league_name_and_standings()
        self.manager_id_name_dict = pd.Series(
            self.standings_df["Manager"].values, index=self.standings_df["ID"]
        ).to_dict()

        ### Dataframe for game week deadlines
        self.bootstrap_static_events_df = pd.DataFrame(
            self._get_requests_response(self.bootstrap_static_url, kwars={})["events"]
        )

        ### Season stats
        with st.spinner(text="(1/2) Collecting and processing season statistics..."):
            self.season_stats_df = self._get_season_stats_df()
        self.max_gw = self.season_stats_df["GW"].max()

        ### Player ID:web_name lookup
        self.player_id_name_dict = self._get_player_id_name_lookup()

        ### Manager teams
        with st.spinner(
            text="(2/2) Collecting and processing team selection data, might take a while..."
        ):
            self.league_teams_df = self._get_teams_dfs()

        ### Transfers
        self.transfers_df = self._get_transfers_df()

        ### Players
        self.players_df = self._get_players_df()

    def add_what_if_managers(self, what_if_gw):
        ### Extend league_teams_df
        self.league_teams_df = self._extend_league_teams_df(what_if_gw)
        ### Season stats
        self.season_stats_df = self._recalc_season_stats(what_if_gw)

        ### Standings

        return None

    def _recalc_season_stats(self, what_if_gw) -> pd.DataFrame:
        ### Merge player points to league_teams_df
        self.league_teams_df = pd.merge(
            left=self.league_teams_df,
            right=self.players_df,
            left_on=["element", "gw"],
            right_on=["player_id", "gw"],
            how="left",
        )

        ### Calculate earned points
        self.league_teams_df["earned_points"] = (
            self.league_teams_df["total_points"] * self.league_teams_df["multiplier"]
        )

        ### Calculate Points
        what_if_season_stats_df = (
            (
                self.league_teams_df.groupby(["Manager", "gw"])["earned_points"]
                .sum()
                .to_frame(name="earned_points")
                .reset_index()
            )
            .rename(columns={"gw": "GW", "earned_points": "Points"})
            .reset_index(drop=True)
        )

        ### Drop non "what if" managers
        what_if_season_stats_df = what_if_season_stats_df[
            what_if_season_stats_df["Manager"].str.contains("(?:what if)")
        ]

        ### Merge in transfers and costs
        what_if_season_stats_df["Manager"] = what_if_season_stats_df[
            "Manager"
        ].str.replace(" (what if)", "")
        what_if_season_stats_df = pd.merge(
            left=what_if_season_stats_df,
            right=self.season_stats_df.loc[
                :,
                [
                    "Manager",
                    "GW",
                    "Transfers",
                    "Transfer Costs",
                    "Total Transfers",
                    "Total Transfer Costs",
                ],
            ],
            on=["Manager", "GW"],
            how="left",
        )
        what_if_season_stats_df["Manager"] = (
            what_if_season_stats_df["Manager"].astype(str) + " (what if)"
        )
        for transfer_col in ["Transfers", "Transfer Costs"]:
            what_if_season_stats_df[transfer_col] = np.where(
                what_if_season_stats_df["GW"] > what_if_gw,
                0,
                what_if_season_stats_df[transfer_col],
            )
        for total_transfer_col in ["Total Transfers", "Total Transfer Costs"]:
            what_if_season_stats_df[total_transfer_col] = np.where(
                what_if_season_stats_df["GW"] > what_if_gw,
                np.nan,
                what_if_season_stats_df[total_transfer_col],
            )
            what_if_season_stats_df[total_transfer_col] = what_if_season_stats_df[
                total_transfer_col
            ].ffill()

        ### Calculate Total Points
        what_if_season_stats_df["Total Points"] = (
            what_if_season_stats_df.groupby(["Manager"])["Points"].transform(
                pd.Series.cumsum
            )
            - what_if_season_stats_df["Total Transfer Costs"]
        )

        ### Concat with regular managers
        recalc_season_stats_df = pd.concat(
            [self.season_stats_df, what_if_season_stats_df],
            ignore_index=True,
            join="outer",
        ).sort_values(by=["Manager", "GW"])

        ### Recalculate league rank as "Rank"
        # recalc_season_stats_df["Rank"] = np.nan
        recalc_season_stats_df["Rank"] = recalc_season_stats_df.groupby("GW")[
            "Total Points"
        ].rank(method="min", ascending=False)

        return recalc_season_stats_df

    def _extend_league_teams_df(self, what_if_gw) -> pd.DataFrame:
        what_if_league_df = self.league_teams_df.copy()
        what_if_league_df["Manager"] = (
            what_if_league_df["Manager"].astype(str) + " (what if)"
        )
        gw_to_repeat = what_if_league_df.loc[what_if_league_df["gw"] == what_if_gw, :]
        repeated_section = pd.concat(
            [gw_to_repeat] * (self.max_gw - what_if_gw),
            ignore_index=True,
        )
        repeated_section["gw"] = np.repeat(
            list(range(what_if_gw + 1, self.max_gw + 1)),
            15 * len(self.manager_id_name_dict),
        )
        repeated_section["player_pick_full"] = list(
            (
                repeated_section["player_pick"] + repeated_section["gw"].astype(str)
            ).values
        )
        what_if_league_df = pd.concat(
            [
                what_if_league_df.loc[what_if_league_df["gw"] <= what_if_gw, :],
                repeated_section,
            ]
        )
        extended_league_teams_df = pd.concat([self.league_teams_df, what_if_league_df])
        return extended_league_teams_df

    def make_season_stats_chart(self, gw_range, y_axis_option):
        if self.season_stats_df["Manager"].str.contains("what if").any():
            colour_list = combined_plotly_colour_list
        else:
            colour_list = hex_plotly_colour_list
        fig = px.line(
            self.season_stats_df[
                self.season_stats_df["GW"].between(gw_range[0], gw_range[1])
            ],
            x="GW",
            y=y_axis_option,
            color="Manager",
            color_discrete_sequence=colour_list,
            markers=True,
        )
        return fig

    def make_similarity_heatmap(self, sim_df):
        heatmap_colourscale = [
            [0, "rgba(61,23,90,255)"],
            [0.35, "rgba(70,160,246,255)"],
            [1, "rgba(72,250,137,255)"],
        ]
        fig = px.imshow(
            sim_df,
            text_auto=False,
            aspect="auto",
            color_continuous_scale=heatmap_colourscale,
            zmax=1.0,
            zmin=0.0,
            labels=dict(x="Manager 1", y="Manager 2", color="Similarity"),
        )
        return fig

    @st.cache_data(ttl=3600, show_spinner=False)
    def make_transfers_fig(self):
        fig = (
            px.scatter(
                self.transfers_df,
                x="time",
                y="Manager",
                color="Manager",
                color_discrete_sequence=px.colors.qualitative.Plotly,
                hover_name=None,
                hover_data={
                    "Manager": True,
                    "time": False,
                    "Player_in": True,
                    "Player_in_cost": True,
                    "Player_out": True,
                    "Player_out_cost": True,
                    "GW": False,
                },
            )
            .update_xaxes(
                rangeslider_visible=True,
                range=[
                    str(
                        self.bootstrap_static_events_df.loc[
                            self.max_gw - 2, "deadline_time"
                        ]
                    )[:10],
                    str(
                        self.bootstrap_static_events_df.loc[
                            self.max_gw, "deadline_time"
                        ]
                    )[:10],
                ],
            )
            .update_layout(
                showlegend=True, yaxis_type="category", hovermode="x unified"
            )
        )
        for gw in range(1, 39):
            fig.add_vline(
                x=datetime.datetime.strptime(
                    self.bootstrap_static_events_df.loc[gw - 1, "deadline_time"], "%Y-%m-%dT%H:%M:%SZ"  # type: ignore
                ).timestamp()
                * 1000,
                line_width=1,
                line_dash="dash",
                line_color="red",
                annotation_text=f"Gameweek {gw} Deadline",
                annotation_position="top",
            )
        return fig

    @st.cache_data(ttl=3600, show_spinner=False)
    def _get_players_df(self):
        all_players_all_gw_list = []
        for gw in range(1, self.max_gw + 1):
            response_json = self._get_requests_response(
                url_template=self.live_url_template, gw=gw
            )
            all_players_dict_list = []
            for result_dict in response_json["elements"]:
                player_id = result_dict["id"]
                stats_dict = result_dict["stats"]
                stats_dict["player_id"] = player_id
                stats_dict["web_name"] = self.player_id_name_dict[player_id]
                all_players_dict_list.append(stats_dict)
            all_players_df = pd.DataFrame(all_players_dict_list)
            all_players_df["gw"] = gw
            all_players_all_gw_list.append(all_players_df)
        players_df = (
            pd.concat(all_players_all_gw_list)
            .loc[:, ["player_id", "web_name", "gw", "total_points"]]
            .reset_index(drop=True)
        )
        return players_df

    @st.cache_data(ttl=3600, show_spinner=False)
    def _get_transfers_df(self) -> pd.DataFrame:
        transfers_dfs_list = []
        for i, (manager_id, manager_name) in enumerate(
            self.manager_id_name_dict.items()
        ):
            transfers_response_json = self._get_requests_response(
                self.transfers_url_template, manager_id=manager_id
            )
            if not transfers_response_json:
                continue
            transfers_per_manager_df = pd.DataFrame(transfers_response_json)
            transfers_per_manager_df["element_in"] = transfers_per_manager_df[
                "element_in"
            ].map(self.player_id_name_dict)
            transfers_per_manager_df["element_in_cost"] = (
                transfers_per_manager_df["element_in_cost"] * 1e5
            ).apply(lambda n: utils.human_readable(n))
            transfers_per_manager_df["element_out"] = transfers_per_manager_df[
                "element_out"
            ].map(self.player_id_name_dict)
            transfers_per_manager_df["element_out_cost"] = (
                transfers_per_manager_df["element_out_cost"] * 1e5
            ).apply(lambda n: utils.human_readable(n))
            transfers_per_manager_df["manager_id"] = manager_id
            transfers_per_manager_df["Manager"] = manager_name
            transfers_dfs_list.append(transfers_per_manager_df)
        transfers_df = pd.concat(transfers_dfs_list).rename(
            columns=col_name_change_dict
        )
        return transfers_df

    @st.cache_data(ttl=3600, show_spinner=False)
    def _get_teams_dfs(self) -> pd.DataFrame:
        league_teams_df_list = []
        league_picks_dict = {}
        managers_completed = st.empty()
        gws_completed = st.empty()
        percent_completed = st.empty()
        prog_bar = st.progress(0)
        for i, (manager_id, manager_name) in enumerate(
            self.manager_id_name_dict.items()
        ):
            league_picks_dict[manager_name] = []
            managers_completed.text(
                "({0}/{1}) Managers completed".format(i, len(self.manager_id_name_dict))
            )
            for j, gw in enumerate(range(1, self.max_gw + 1)):
                team_selection_response_json = self._get_requests_response(
                    self.picks_url_template, manager_id=manager_id, gw=gw
                )
                picks_df = pd.DataFrame(team_selection_response_json["picks"])
                picks_df["player_name"] = picks_df["element"].map(
                    self.player_id_name_dict
                )
                picks_df["Manager"] = manager_name
                picks_df["gw"] = gw
                picks_df["status"] = np.where(
                    (picks_df["is_captain"] == True) & (picks_df["multiplier"] == 2),
                    "c",
                    np.where(
                        (picks_df["is_captain"] == True)
                        & (picks_df["multiplier"] == 3),
                        "tc",
                        np.where(
                            picks_df["is_vice_captain"] == True,
                            "v",
                            np.where(
                                (picks_df["multiplier"] == 0)
                                | (picks_df["position"].isin([12, 13, 14, 15])),
                                "b",
                                "p",
                            ),
                        ),
                    ),
                )
                picks_df["player_pick"] = list(
                    (
                        picks_df["player_name"]
                        + " ("
                        + picks_df["status"].astype(str)
                        + ")"
                    ).values
                )
                picks_df["player_pick_full"] = list(
                    (picks_df["player_pick"] + picks_df["gw"].astype(str)).values
                )
                league_teams_df_list.append(picks_df)
                gws_completed.text(
                    "({0}/{1}) Gameweeks completed".format(j, self.max_gw)
                )
                percent_completed.text(
                    "{0:.3f} %".format(
                        100
                        * (
                            ((i * self.max_gw) + (j + 1))
                            / (len(self.manager_id_name_dict) * self.max_gw)
                        )
                    )
                )
                prog_bar.progress(
                    ((i * self.max_gw) + (j + 1))
                    / (len(self.manager_id_name_dict) * self.max_gw)
                )

        managers_completed.empty()
        gws_completed.empty()
        percent_completed.empty()
        prog_bar.empty()

        league_teams_df = pd.concat(league_teams_df_list).reset_index(drop=True)
        return league_teams_df

    @st.cache_data(ttl=3600, show_spinner=False)
    def _get_season_stats_df(self) -> pd.DataFrame:
        season_stats_list = []
        managers_completed = st.empty()
        percent_completed = st.empty()
        prog_bar = st.progress(0)
        for i, (manager_id, manager_name) in enumerate(
            self.manager_id_name_dict.items()
        ):
            history_response_json = self._get_requests_response(
                self.history_url_template, manager_id=manager_id
            )
            season_stats_per_manager_df = pd.DataFrame(history_response_json["current"])
            season_stats_per_manager_df["ID"] = manager_id
            season_stats_per_manager_df["Manager"] = manager_name
            season_stats_list.append(season_stats_per_manager_df)
            managers_completed.text(
                "({0}/{1}) Managers completed".format(i, len(self.manager_id_name_dict))
            )
            percent_completed.text(
                "{0:.3f} %".format(100 * ((i + 1) / len(self.manager_id_name_dict)))
            )
            prog_bar.progress((i + 1) / len(self.manager_id_name_dict))
        managers_completed.empty()
        percent_completed.empty()
        prog_bar.empty()
        season_stats_df = (
            pd.concat(season_stats_list)
            .rename(columns=col_name_change_dict)
            .drop(["Rank", "Rank Sort"], axis=1)
        )
        ### Divide by 10
        season_stats_df["Bank"] = season_stats_df["Bank"] * 1e5
        season_stats_df["Value"] = season_stats_df["Value"] * 1e5
        ### Add league rank as "Rank"
        season_stats_df["Rank"] = np.nan
        season_stats_df["Rank"] = season_stats_df.groupby("GW")["Total Points"].rank(
            method="min", ascending=False
        )
        ### Add "Total" columns
        for col in ["Transfers", "Transfer Costs", "Points on Bench"]:
            season_stats_df[f"Total {col}"] = season_stats_df.groupby("Manager")[
                col
            ].cumsum()
        ### Add "Form" column
        season_stats_df["Form"] = season_stats_df.groupby("Manager")[
            "Points"
        ].transform(lambda s: s.rolling(4, min_periods=1).mean().div(12))
        return season_stats_df.sort_values(by=["Manager", "GW"])

    @st.cache_data
    def _get_league_name_and_standings(self) -> tuple:
        fpl_league_response_json = self._get_requests_response(
            self.standings_url_template, leagueID=self.leagueID
        )
        league_name = fpl_league_response_json["league"]["name"]
        standings_df = pd.DataFrame(
            fpl_league_response_json["standings"]["results"]
        ).rename(columns=col_name_change_dict)
        return league_name, standings_df

    @st.cache_data
    def _get_player_id_name_lookup(self) -> dict:
        bootstrap_static_response = self._get_requests_response(
            self.bootstrap_static_url, kwars={}
        )
        elements_df = pd.DataFrame(bootstrap_static_response["elements"])
        player_id_name_dict = pd.Series(
            elements_df["web_name"].values, index=elements_df["id"]
        ).to_dict()
        return player_id_name_dict

    def _get_requests_response(self, url_template, **kwargs) -> dict:
        response = requests.get(url_template.format(**kwargs))
        response_json = response.json()
        return response_json
